# 子智能体与异步通知实现说明

本文档汇总 `src/tools/AgentTool`、`src/tasks/LocalAgentTask`、`src/query.ts`、`src/utils/messageQueueManager.ts` 这一组代码中，子智能体尤其是“异步子智能体完成后如何通知主智能体”的实现逻辑。

## 1. 整体分层

这套实现可以分成 4 层：

1. `AgentTool`
负责解析输入、选择 agent、决定同步/异步/隔离模式，并启动子智能体。

2. `runAgent`
真正驱动子智能体执行 `query()` 循环，负责上下文隔离、工具池、权限模式、transcript 落盘、hooks、skills、MCP 等细节。

3. `LocalAgentTask`
负责异步子智能体的生命周期管理，包括：
- 后台任务注册
- 进度更新
- 完成/失败/停止状态切换
- 生成完成通知

4. 统一消息队列 + 主线程 query 注入
异步任务结束后，不直接“回调”主智能体，而是生成一条 `task-notification` 放入统一队列；主线程在空闲态或下一次 query 检查点把它重新注入模型上下文。

## 2. AgentTool 是入口层，不是执行层

核心入口：
- `src/tools/AgentTool/AgentTool.tsx`

`AgentTool.call()` 的职责：

- 解析输入参数：
  - `prompt`
  - `subagent_type`
  - `run_in_background`
  - `isolation`
  - `cwd`
  - `name/team_name`（用于 teammate/team 模式）
- 决定走哪条路径：
  - 普通 specialized subagent
  - fork subagent
  - sync 执行
  - async 执行
  - worktree 隔离
  - remote 隔离
- 为 worker 组装独立工具池
- 在 async 模式下注册后台任务并启动后台生命周期

关键点：

- `AgentTool` 自己不承载子智能体完整执行状态。
- 它更像 orchestration 层，负责“如何启动”，而不是“如何跑完整个 agent 回合”。

## 3. 子智能体真正执行在 runAgent

核心文件：
- `src/tools/AgentTool/runAgent.ts`

`runAgent()` 是子智能体真正的执行器，主要负责：

- 解析模型
- 创建 `agentId`
- 准备 prompt messages
- 根据 agent 定义调整 permission mode
- 初始化 agent 专属 MCP servers
- 预加载 agent frontmatter 中声明的 skills
- 注册 frontmatter hooks
- 创建独立的 `ToolUseContext`
- 调用底层 `query()` 执行 LLM 回合
- 持续记录 sidechain transcript
- 收尾清理

### 3.1 上下文隔离

隔离逻辑主要在：
- `src/utils/forkedAgent.ts`

`createSubagentContext()` 默认会：

- 克隆 `readFileState`
- 克隆或重建 `contentReplacementState`
- 创建新的 `AbortController`
- 创建新的 `queryTracking`
- 创建新的 `localDenialTracking`
- 把大多数会影响父上下文的回调替换成 no-op

只有显式声明共享时才会共用父上下文能力，例如：
- `shareSetAppState`
- `shareSetResponseLength`
- `shareAbortController`

这意味着子智能体默认是“隔离执行”的，而不是和主智能体共用同一份可变运行状态。

### 3.2 transcript 与 metadata

子智能体不会把所有执行轨迹直接混入主 transcript，而是写入 sidechain transcript：

- transcript 路径管理：
  - `src/utils/sessionStorage.ts`
- 关键函数：
  - `recordSidechainTranscript()`
  - `getAgentTranscriptPath()`
  - `writeAgentMetadata()`
  - `readAgentMetadata()`

metadata 里会保存：
- `agentType`
- `worktreePath`
- `description`

这样在 resume 时可以恢复：
- 原 agent 类型
- 原工作目录
- 原任务描述

## 4. 异步子智能体的生命周期

核心文件：
- `src/tasks/LocalAgentTask/LocalAgentTask.tsx`
- `src/tools/AgentTool/agentToolUtils.ts`

### 4.1 启动

异步子智能体启动时：

1. `AgentTool.call()` 判断 `shouldRunAsync`
2. 调用 `registerAsyncAgent()`
3. 创建 `LocalAgentTaskState`
4. 然后把真正执行逻辑交给 `runAsyncAgentLifecycle()`

`LocalAgentTaskState` 里维护的信息包括：
- `agentId`
- `status`
- `prompt`
- `selectedAgent`
- `abortController`
- `progress`
- `result`
- `notified`
- `pendingMessages`

### 4.2 执行

`runAsyncAgentLifecycle()` 负责：

- 消费 `runAgent()` 产出的消息流
- 持续累积 `agentMessages`
- 更新 `LocalAgentTask.progress`
- 触发 SDK 进度事件
- 在成功/失败/终止时做统一收口

成功路径：

1. `finalizeAgentTool()` 归纳最终结果
2. `completeAsyncAgent()` 标记任务完成
3. 生成最终通知
4. 调用 `enqueueAgentNotification()`

失败路径：

- `failAsyncAgent()`
- `enqueueAgentNotification(status='failed')`

终止路径：

- `killAsyncAgent()`
- `enqueueAgentNotification(status='killed')`

## 5. 异步完成后，如何通知主智能体

这是这一块最关键的设计。

### 5.1 不是直接回调主智能体

异步子智能体结束时，主智能体通常已经结束了启动它的那一轮工具调用。

因此不会存在一个“同步返回值”再直接塞回主智能体函数栈。

系统采用的是：

`后台任务完成 -> 生成 task-notification -> 进入统一队列 -> 主线程在后续时机消费`

### 5.2 通知的生成

核心函数：
- `enqueueAgentNotification()`

它会构造一段 XML，形如：

```xml
<task-notification>
<task-id>...</task-id>
<output-file>...</output-file>
<status>completed|failed|killed</status>
<summary>...</summary>
<result>...</result>
<usage>...</usage>
</task-notification>
```

这段 XML 不是直接送给模型，而是先进入统一命令队列。

### 5.3 进入统一命令队列

核心文件：
- `src/utils/messageQueueManager.ts`

异步子智能体完成通知通过：

- `enqueuePendingNotification({ value, mode: 'task-notification' })`

进入统一队列。

这套队列不是只给 agent 用，而是整个 REPL 共享的统一命令队列。它承载：
- 用户 prompt
- bash 模式输入
- orphaned permission
- task notification

## 6. 队列中的消息类型

队列项的 `mode` 定义在：
- `src/types/textInputTypes.ts`

共有 4 种：

- `prompt`
- `bash`
- `orphaned-permission`
- `task-notification`

同时还有 3 种优先级：

- `now`
  - 立即打断当前操作
- `next`
  - 当前工具调用结束后尽快处理
- `later`
  - 当前 turn 结束后处理

异步子智能体完成通知默认是：
- `mode = 'task-notification'`
- `priority = 'later'`

## 7. 队列消息是否会唤醒主智能体

会，但分情况。

### 7.1 主线程空闲

当主线程空闲时：

- `enqueuePendingNotification()` 会触发队列变更信号
- `useQueueProcessor()` 监听这个变化
- 如果当前没有 active query，就会立刻处理队列

也就是：

`入队 -> React/REPL 监听到队列变化 -> 启动新的输入处理 -> 进入新一轮 query`

### 7.2 主线程正在 query

如果主线程已经在一轮 query 里，`task-notification` 默认不会像 `priority='now'` 一样立即中断。

它会在 query 的检查点被消费：

- `query.ts` 每轮在调用模型前会读取队列里的 `task-notification`
- 然后把它们转成 attachment 注入当前/下一次模型调用

因此这类通知通常是：

- 不强制中断
- 但会在后续安全时机尽快进入模型上下文

### 7.3 主线程在 Sleep

队列优先级定义里已经写明：

- `next` 会唤醒进行中的 `Sleep`
- `later` 也会唤醒进行中的 `Sleep`

所以在 proactive/Sleep 场景下，异步任务完成通知会使主线程提前醒来处理后续逻辑。

## 8. 主线程如何把通知送给模型

核心文件：
- `src/query.ts`
- `src/utils/attachments.ts`
- `src/utils/messages.ts`

主线程不是直接把队列里的原始 XML 文本扔给模型，而是走一层“attachment -> user-side message”的转换。

流程如下：

1. `query.ts` 在回合检查点读取队列中的 `task-notification`
2. `attachments.ts` 把它转成 `queued_command` attachment
3. `messages.ts` 再把它包装成最终送给模型的用户侧消息

## 9. 为什么模型不会把它完全当成普通用户输入

虽然这条消息在线路上最终会进入“用户侧消息流”，但它不是裸的用户自然语言输入。

系统用了几层信号来降低误解概率：

### 9.1 明确的 origin

`queued_command` 转换时会把它标记为：

- `origin.kind = 'task-notification'`

而不是 `human`

### 9.2 文本包装

在 `messages.ts` 中，这类消息会被包装为：

```text
A background agent completed a task:
...
```

这会显式告诉模型：

- 这是后台 agent 的完成事件
- 不是用户刚刚提出了一个新问题

### 9.3 XML 结构本身带有强机器信号

通知正文是 `<task-notification>` 这样的结构化 XML，不像普通自然语言 prompt。

### 9.4 coordinator mode 的 system prompt 明确约束

在 coordinator prompt 中，系统直接告诉模型：

- worker results 和 system notifications 是 internal signals
- 它们看起来像 user-role messages，但并不是真正的用户输入

因此，这套实现并不是依赖 role 区分，而是依赖：

- origin
- 包装文本
- XML 结构
- system prompt 约束

共同降低偏差。

## 10. 为什么不用迟到的 tool_result

从架构上说，异步子智能体完成结果不适合直接建模成“晚到的 `tool_result`”。

原因有三点：

1. 原始工具调用早就结束了
`AgentTool` 启动异步任务时，那一轮工具调用已经返回了 `async_launched`，后续完成结果已经不在同一个 tool round-trip 内。

2. 单独的 SDK/system event 只会通知 UI，不会驱动主模型继续思考
这条通道适合面板、编辑器、桥接层，不适合作为模型继续决策的输入。

3. 当前架构里，统一队列 + `task-notification` 已经是“异步结果重新进入主模型上下文”的标准入口

所以设计上选择了：

- 不伪造迟到的 `tool_result`
- 而是用一条新的 `task-notification` 作为跨回合异步事件

## 11. 为什么不是单独的 system role

原因不是“不能做”，而是“当前架构里 user-side queued command 才是稳定可复用的注入通道”。

现有 REPL/query 管线天然支持：

- 队列里来一条命令
- 转成 attachment
- 再进入下一轮模型上下文

如果只发一个 UI 层 system event：

- 前端会知道任务完成
- 但主模型未必会重新获得这个信息并继续推理

因此这里借用的是“用户侧输入通道”，但通过 origin 和包装文本保留了“这其实是系统内部事件”的语义。

## 12. fork 子智能体的特殊点

fork 子智能体是 `AgentTool` 的一个特殊分支：

- 没显式传 `subagent_type`
- 且 fork feature 开启

就会走 `FORK_AGENT`。

它的特点：

- 继承父系统 prompt
- 继承父 conversation context
- 继承父工具定义
- 尽可能保持 prompt cache 前缀一致

它和普通 specialized subagent 的最大区别在于：

- 目标不是“切换到另一个 agent persona”
- 而是“在最大程度继承当前上下文的情况下 fork 一个 worker”

这也是为什么 fork 路径对：
- tool definitions
- system prompt bytes
- tool_result 占位

都格外敏感。

## 13. 关键文件索引

入口与编排：
- `src/tools/AgentTool/AgentTool.tsx`

实际执行：
- `src/tools/AgentTool/runAgent.ts`

异步生命周期：
- `src/tools/AgentTool/agentToolUtils.ts`
- `src/tasks/LocalAgentTask/LocalAgentTask.tsx`

fork 逻辑：
- `src/tools/AgentTool/forkSubagent.ts`

agent 定义加载：
- `src/tools/AgentTool/loadAgentsDir.ts`
- `src/tools/AgentTool/builtInAgents.ts`

上下文隔离：
- `src/utils/forkedAgent.ts`

队列与消息注入：
- `src/utils/messageQueueManager.ts`
- `src/utils/attachments.ts`
- `src/utils/messages.ts`
- `src/query.ts`
- `src/hooks/useQueueProcessor.ts`

## 14. 一句话总结

这套子智能体实现，本质上是：

“由 `AgentTool` 编排、由 `runAgent()` 执行、由 `LocalAgentTask` 管理生命周期、并通过 `task-notification` 把异步结果重新注入主模型上下文的一套多回合子代理机制。”

而异步完成通知的关键并不是“直接回调主智能体”，而是：

“把子智能体结果转成一条结构化系统通知，进入统一队列，再由主线程在后续安全时机重新吸收到模型上下文中。”
