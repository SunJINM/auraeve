# Claude Code 子智能体系统设计文档

## 1. 架构总览

Claude Code 的子智能体系统采用**四层分离架构**：

```
┌─────────────────────────────────────────────┐
│  入口层 (AgentTool)                          │
│  参数解析 → 模式决策 → 工具池组装 → 生命周期选择  │
├─────────────────────────────────────────────┤
│  执行层 (runAgent)                           │
│  上下文隔离 → MCP初始化 → Query循环驱动        │
├─────────────────────────────────────────────┤
│  生命周期层 (LocalAgentTask)                  │
│  任务注册 → 进度追踪 → 完成/失败/终止处理       │
├─────────────────────────────────────────────┤
│  通知层 (MessageQueue + Query注入)            │
│  task-notification → 统一队列 → 模型上下文注入   │
└─────────────────────────────────────────────┘
```

## 2. Agent 定义系统

### 2.1 类型体系

```
BaseAgentDefinition（共同字段）
├── BuiltInAgentDefinition（内置，getSystemPrompt 动态生成）
├── CustomAgentDefinition（用户自定义，从文件加载）
└── AgentDefinition = BuiltInAgentDefinition | CustomAgentDefinition
```

### 2.2 Agent 定义关键字段

| 字段 | 类型 | 说明 |
|------|------|------|
| agentType | string | Agent 标识符（如 "general-purpose"、"Explore"） |
| whenToUse | string | 使用场景描述，供主 Agent 选择 |
| tools | string[] | 可用工具列表，支持通配符 `*` 表示全部 |
| disallowedTools | string[] | 禁止工具列表 |
| model | string | 模型选择，支持 "inherit" 继承父 Agent |
| permissionMode | string | 权限模式：bubble/plan/acceptEdits/auto/bypassPermissions |
| maxTurns | number | 最大对话轮数 |
| isolation | string | 隔离方式：worktree |
| skills | string[] | 预加载的技能列表 |
| hooks | object | 会话级钩子（SubagentStart/SubagentStop） |

### 2.3 内置 Agent 类型

| 类型 | 用途 | 工具池 | 权限模式 |
|------|------|--------|---------|
| general-purpose | 通用目的，研究+执行 | * (全部) | 继承父 |
| Explore | 只读搜索，快速探索代码 | Read/Grep/Glob/WebFetch/WebSearch 等只读工具 | bypassPermissions |
| Plan | 计划编制 | 只读工具（不含编辑/写入） | bypassPermissions |
| Verification | 验证 agent | 只读工具 | bypassPermissions |

### 2.4 用户自定义 Agent

通过 `.claude/agents/` 目录加载 Markdown 文件，frontmatter 定义配置：

```markdown
---
agentType: my-agent
whenToUse: 当需要执行特定任务时
tools:
  - Read
  - Bash(grep, find)
  - Glob
model: inherit
permissionMode: plan
maxTurns: 20
---

你是一个专门执行 XX 任务的 agent...
```

加载流程：扫描目录 → 解析 frontmatter → 验证工具规范 → 注册到可用 Agent 列表。

## 3. 入口层：AgentTool

### 3.1 核心职责

AgentTool 是用户（主 Agent）调用子智能体的唯一入口，负责：

1. **参数解析**：prompt、subagent_type、run_in_background、isolation、model
2. **Agent 选择**：根据 subagent_type 匹配已注册的 Agent 定义
3. **模式决策**：同步 vs 异步 vs worktree 隔离
4. **工具池组装**：为子智能体构建独立的工具集
5. **生命周期启动**：同步直接执行 / 异步注册后台任务

### 3.2 执行路径选择

```
AgentTool.call()
  │
  ├─ 解析参数 (prompt, subagent_type, run_in_background, isolation)
  │
  ├─ 选择 Agent 定义 (matchAgentType)
  │
  ├─ MCP 服务器检查 (requiredMcpServers)
  │
  ├─ Worktree 隔离? ──→ 创建 git worktree
  │
  ├─ 组装工具池 (resolveAgentTools + filterToolsForAgent)
  │
  ├─ 判断同步/异步 (shouldRunAsync)
  │   │
  │   ├─ 同步 ──→ runAgent() 直接执行，等待结果返回
  │   │
  │   └─ 异步 ──→ registerAsyncAgent()
  │              → runAsyncAgentLifecycle() 后台驱动
  │              → 立即返回 "已启动" 提示
  │
  └─ 返回结果（同步）或启动确认（异步）
```

### 3.3 同步/异步判断条件

```
shouldRunAsync = (
    run_in_background === true       // 用户显式指定
    || selectedAgent.background      // Agent 定义指定后台运行
) && !isBackgroundTasksDisabled      // 未禁用后台任务
```

## 4. 工具池管理

### 4.1 工具过滤层次

```
所有可用工具
  │
  ├─ 1. Agent 定义 tools/disallowedTools 过滤
  │     tools: ["Read", "Grep", "Bash(grep, find)"]
  │     disallowedTools: ["AgentTool"]
  │
  ├─ 2. 内置禁止列表 (ALL_AGENT_DISALLOWED_TOOLS)
  │     - AgentTool（防止递归，除非显式允许）
  │     - AskUserQuestion（子智能体不能向用户提问）
  │     - TaskStop
  │     - ExitPlanMode / EnterPlanMode
  │
  ├─ 3. 异步专属白名单 (ASYNC_AGENT_ALLOWED_TOOLS)
  │     异步子智能体只能使用安全的工具子集：
  │     - FileRead, Grep, Glob, WebSearch, WebFetch
  │     - Bash, FileEdit, FileWrite
  │     - TodoWrite, Skill, NotebookEdit
  │
  └─ 最终工具池
```

### 4.2 工具规范解析

支持带参数限制的工具声明：

```
"Bash"              → 全部 Bash 权限
"Bash(grep, find)"  → 只允许 grep 和 find 命令
"Agent(Explore)"    → 只允许调用 Explore 类型子智能体
"*"                 → 通配符，展开为所有允许的工具
```

## 5. 执行层：runAgent

### 5.1 核心职责

runAgent 是子智能体的实际执行器，驱动 LLM 对话循环：

1. 创建唯一 agentId
2. 构建系统提示（Agent 定义 + 上下文）
3. 创建隔离的 ToolUseContext
4. 初始化 Agent 专属 MCP 服务器
5. 预加载 frontmatter 中声明的 skills
6. 调用底层 query() 执行 LLM 回合循环
7. 记录 sidechain transcript
8. 收尾清理（MCP 断开、资源释放）

### 5.2 上下文隔离机制

通过 `createSubagentContext()` 实现细粒度的状态隔离：

| 状态域 | 默认行为 | 说明 |
|--------|---------|------|
| readFileState | 克隆 | 文件读取状态独立 |
| abortController | 新建子 controller | 独立的中止控制 |
| setAppState | no-op | 不影响父 Agent UI 状态 |
| setResponseLength | no-op | 不影响父 Agent 响应长度 |
| contentReplacementState | 克隆 | 内容替换规则独立 |
| queryTracking | 新建 | 独立的查询追踪 |

**关键设计原则**：子智能体默认完全隔离，不会影响父 Agent 的任何可变状态。只有通过显式的 `share*` 标志才能 opt-in 共享。

### 5.3 Transcript 记录

子智能体不混入主 transcript，而是写入独立的 sidechain transcript：

- 路径：`{sessionDir}/agents/{agentId}.jsonl`
- 内容：完整的消息历史（assistant + tool_use + tool_result）
- metadata：agentType、description、worktreePath

## 6. 生命周期层：LocalAgentTask

### 6.1 任务状态

```typescript
interface LocalAgentTaskState {
  agentId: string
  agentType: string
  prompt: string
  description: string
  status: 'running' | 'completed' | 'failed' | 'killed'
  progress: ProgressTracker
  result?: string
  pendingMessages: Message[]
  isBackgrounded: boolean
}
```

### 6.2 进度追踪

```typescript
interface ProgressTracker {
  toolUseCount: number              // 工具调用次数
  latestInputTokens: number         // 最新输入 token 数
  cumulativeOutputTokens: number    // 累计输出 token 数
  recentActivities: ToolActivity[]  // 最近 5 个工具活动
}

interface ToolActivity {
  toolName: string                  // 工具名称
  input: Record<string, unknown>    // 工具输入参数
  activityDescription?: string      // "Reading src/foo.ts"
}
```

### 6.3 异步生命周期驱动

```
registerAsyncAgent() → 创建 LocalAgentTaskState
        │
        ↓
runAsyncAgentLifecycle()
        │
        ├─ 消费 runAgent() 产出的消息流
        │
        ├─ 每条消息 → updateAsyncAgentProgress()
        │
        ├─ 成功 → finalizeAgentTool() → completeAsyncAgent()
        │         → enqueueAgentNotification(status='completed')
        │
        ├─ 失败 → failAsyncAgent()
        │         → enqueueAgentNotification(status='failed')
        │
        └─ 终止 → killAsyncAgent()
                  → enqueueAgentNotification(status='killed')
```

## 7. 通知层：异步结果如何回到主智能体

### 7.1 设计原则

异步子智能体完成时，主智能体通常已结束启动它的那轮工具调用。因此不能用同步返回值。

采用的方案：**task-notification → 统一队列 → 主线程在后续安全时机消费**。

### 7.2 统一命令队列

```
commandQueue: QueuedCommand[]

QueuedCommand {
  priority: 'now' | 'next' | 'later'
  value: string | ContentBlock[]
  mode: 'prompt' | 'task-notification' | 'bash' | 'orphaned-permission'
}
```

队列不是专为 agent 设计的，而是整个 REPL 共享的统一输入通道：
- `prompt`：用户输入
- `task-notification`：异步任务完成通知
- `bash`：bash 模式输入
- `orphaned-permission`：孤立的权限请求

### 7.3 通知消息格式

```xml
<task-notification>
  <task-id>{taskId}</task-id>
  <tool-use-id>{toolUseId}</tool-use-id>
  <output-file>{sidechain transcript 路径}</output-file>
  <status>completed|failed|killed</status>
  <summary>{description}</summary>
  <result>{最终结果文本}</result>
  <usage>
    <total_tokens>{n}</total_tokens>
    <tool_uses>{n}</tool_uses>
    <duration_ms>{ms}</duration_ms>
  </usage>
  <worktree>
    <path>{worktree 路径}</path>
    <branch>{分支名}</branch>
  </worktree>
</task-notification>
```

### 7.4 通知消费时机

| 主线程状态 | 消费方式 |
|-----------|---------|
| 空闲 | 队列变更信号触发 → 立即处理 → 启动新一轮 query |
| 正在 query | query 检查点读取 → 转为 attachment → 注入当前/下一次模型调用 |
| Sleep 中 | later 优先级也会唤醒 Sleep → 提前处理 |

### 7.5 注入模型上下文的流程

```
task-notification 入队
  ↓
query.ts 在回合检查点读取队列中的 task-notification
  ↓
attachments.ts 转为 queued_command attachment
  ↓
messages.ts 包装为用户侧消息：
  "A background agent completed a task: ..."
  ↓
origin.kind = 'task-notification'（非 human）
  ↓
模型收到消息，识别为系统内部事件而非用户提问
```

### 7.6 防止模型误解的多重保障

1. **origin 标记**：`origin.kind = 'task-notification'` 而非 `human`
2. **文本包装**：`"A background agent completed a task:"`
3. **XML 结构**：`<task-notification>` 结构化格式
4. **system prompt 约束**：明确告知模型这是 internal signal

## 8. Worktree 隔离

### 8.1 创建流程

```
用户指定 isolation: "worktree"
  ↓
生成 slug: agent-{agentId前8位}
  ↓
createAgentWorktree(slug)
  ├── 创建独立 git worktree
  ├── 记录 headCommit（用于变更检测）
  └── 返回 {worktreePath, worktreeBranch, headCommit}
  ↓
runAgent() 在 worktreePath 下执行
  ↓
完成后检查变更
  ├── 无变更 → 自动清理 worktree
  └── 有变更 → 保留 worktree，返回路径和分支名给用户
```

### 8.2 设计意图

- 文件操作完全隔离，不影响主工作目录
- 适合并行修改不同文件集的场景
- 无变更时自动清理，避免 worktree 堆积

## 9. 权限模式

### 9.1 模式定义

| 模式 | 行为 |
|------|------|
| auto | 分类器自动判断是否需要用户确认 |
| acceptEdits | 接受所有编辑操作（默认） |
| plan | 要求用户批准计划后再执行 |
| ask | 每个操作逐一询问用户 |
| bypassPermissions | 完全跳过权限检查（只读 Agent 适用） |
| bubble | 冒泡到父 Agent 的 terminal 显示权限提示 |

### 9.2 子智能体权限处理

```
Agent 定义的 permissionMode
  ↓
是否为异步?
  ├─ 异步 → 自动禁用 UI 权限提示（shouldAvoidPrompts = true）
  │         工具调用依赖预设的 allow 规则
  └─ 同步 → 可以 bubble 到父 terminal 显示提示
```

## 10. 关键设计决策总结

### 10.1 为什么不用迟到的 tool_result

原始工具调用已返回 `async_launched`，后续结果不在同一个 tool round-trip 内。使用 task-notification 作为跨回合异步事件更合理。

### 10.2 为什么不用 system role

现有 query 管线天然支持 "队列 → attachment → 模型上下文"。system event 只通知 UI，不驱动模型继续推理。

### 10.3 为什么默认隔离

子智能体可能并发执行，共享可变状态会导致竞态。默认隔离 + 显式共享是最安全的设计。

### 10.4 为什么子智能体不能递归派发

防止无限递归消耗资源。AgentTool 在子智能体的工具池中默认被禁止（除非 Agent 定义显式允许并限制可调用的类型）。

## 11. 文件索引

| 文件 | 职责 |
|------|------|
| src/tools/AgentTool/AgentTool.tsx | 入口层：参数、模式决策、生命周期选择 |
| src/tools/AgentTool/runAgent.ts | 执行层：上下文隔离、Query 循环驱动 |
| src/tools/AgentTool/agentToolUtils.ts | 工具过滤、权限判断、异步生命周期驱动 |
| src/tools/AgentTool/loadAgentsDir.ts | Agent 定义加载、解析、验证 |
| src/tools/AgentTool/builtInAgents.ts | 内置 Agent 注册 |
| src/tasks/LocalAgentTask/LocalAgentTask.tsx | 任务状态、进度追踪、通知生成 |
| src/utils/forkedAgent.ts | 上下文隔离、SubagentContext 创建 |
| src/utils/messageQueueManager.ts | 统一命令队列、优先级管理 |
| src/utils/attachments.ts | 通知转 attachment |
| src/query.ts | 队列消费、attachment 注入模型上下文 |
