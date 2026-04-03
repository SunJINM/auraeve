# AuraEve 聊天页对齐 Claude Code 设计

日期: 2026-04-03
状态: 已在对话中确认方向，等待用户审阅书面设计稿

## 摘要

AuraEve 将重构当前 WebUI 聊天页，使其在信息组织、消息类型、运行流展示方式上尽量对齐 Claude Code，同时保留 AuraEve 现有的 WebUI 主题、配色、玻璃态风格与整体视觉语言。

重构后的聊天页不再采用“左侧聊天区 + 右侧运行控制台”的结构，而改为单一 transcript 驱动的运行界面。所有关键运行信息都回到主消息流中展示，包括：

- 用户消息
- 助手回复
- 运行状态
- 工具调用与结果
- 子智能体启动、运行、完成与失败
- 系统提示与错误
- 连续低价值搜索/读取活动的折叠摘要

当前通用智能体场景不包含审批授权，因此聊天页设计中不再保留审批相关 UI、接口字段与消息类型。

## 目标

- 让聊天页的主阅读路径对齐 Claude Code 的 transcript-first 模型
- 将“智能体正在做什么”直接显示在主消息流中，而不是堆到独立侧栏
- 将工具调用、子智能体过程、系统状态统一建模为可渲染消息块
- 支持展开查看某个工具或某个子智能体的详细过程
- 自动折叠连续、低价值、刷屏式的读取与搜索活动
- 保持 AuraEve 当前 WebUI 的主题、视觉风格与页面外壳

## 非目标

- 不对齐 Claude Code 的终端外观、键盘快捷键体系或 Transcript 搜索能力
- 不引入模型选择、thinking toggle、权限模式切换等 AuraEve 当前没有的功能
- 不保留当前聊天页右侧运行控制台作为长期兼容层
- 不在本次设计中覆盖整个 WebUI 的导航、侧边栏或页面壳子重构
- 不保留审批中心、审批消息块或审批浮层

## 设计原则

本次设计遵循以下原则：

- 主线优先，细节后置
- 过程可见，但不刷屏
- 所有运行态都必须可被解释为消息块
- 默认简洁，按需展开
- 删除无用并列面板，而不是继续往面板里堆信息
- 保留 AuraEve 视觉语言，只替换聊天页的信息结构

## Claude Code UI 深度分析

### 1. 主布局模型

Claude Code 的 UI 核心不是多面板控制台，而是一个统一的主 transcript。界面结构可以抽象为三层：

- 顶部或中部的可滚动消息区
- 底部固定输入区
- 覆盖其上的 overlay 或 modal

它通过少量辅助机制增强长对话体验，而不是增加常驻信息面板：

- 未读分隔线
- “new messages” pill
- 粘性 prompt header
- 虚拟滚动
- transcript 展开视图

这些能力都围绕“如何读同一条消息流”设计，而不是围绕“如何在多块面板之间切换”设计。

### 2. 消息不是单一气泡，而是消息块系统

Claude Code 的顶层消息至少包括：

- attachment
- assistant
- user
- system
- grouped_tool_use
- collapsed_read_search

其中 assistant 内部继续拆块：

- text
- tool_use
- thinking
- redacted_thinking
- server/advisor 相关块

这意味着 Claude Code 在数据层已经放弃“一个 assistant 回复 = 一个气泡”的模型，转而采用“一个 assistant 回合 = 一组语义块”的模型。

### 3. 工具调用的展示重点是运行态，不是参数

Claude Code 的工具调用块优先表达：

- 正在做什么
- 是否还在执行
- 是否排队
- 是否等待权限
- 是否完成
- 是否出错

而不是直接把工具参数平铺到屏幕上。

运行中的 tool_use 会显示进度文案。等待权限、排队、已完成都会使用不同状态视图。工具结果也不是简单拼接到 assistant 文本后，而是作为独立结果块回到消息流中。

### 4. 低价值活动会自动折叠

Claude Code 会把连续的读取、搜索、列表、部分 Bash、MCP 查询折叠成一个摘要组，而不是逐条刷屏。

折叠规则的关键特征：

- 连续同类 search/read 活动按组聚合
- REPL 包装器、Snip、ToolSearch 这类元操作会被静默吸收
- 搜索、读取、列目录、普通 Bash 会分开计数
- 展开前只显示摘要和最近提示
- 展开后才能看到内部原始过程

这套机制决定了 Claude Code 即使工具很多，主界面仍然可读。

### 5. 子智能体是主线中的可展开运行单元

Claude Code 不把子智能体做成侧栏，也不把它当作日志面板的一部分。它把子智能体建模为一种特殊消息块：

- 启动时显示已派出
- 运行中显示进度摘要
- 完成后显示总结信息
- 支持展开查看完整 transcript

展开后的子智能体过程仍然使用同样的消息块语言，而不是跳转到另一套完全不同的界面模型。

### 6. Claude Code 的清晰感来自信息分层

Claude Code 清晰，不是因为它显示的信息少，而是因为它做了以下分层：

- 主线只显示当前用户真正需要读的内容
- 低价值过程被折叠
- 细节通过展开查看
- 所有状态围绕本次运行组织
- 工具、子智能体、系统状态都通过同一套 transcript 被理解

## AuraEve 当前聊天页问题

当前聊天页的主要问题不是样式，而是信息结构：

- 左右分栏让用户必须在“聊天主线”和“运行面板”之间来回切换
- 右侧运行控制台把工具调用、子体任务、节点状态、时间线并列平铺，流程感弱
- 主消息流只有普通 user/assistant 气泡，无法承载运行过程
- 后端事件粒度过粗，前端只能通过快照拼面板
- 审批、节点、时间线在当前通用智能体场景下属于低价值甚至无价值信息

## 目标界面

### 1. 页面骨架

新的聊天页只保留三个一级区域：

- 顶部轻量运行头
- 中间统一 transcript
- 底部固定 composer

删除项：

- 当前右侧运行控制台整栏
- 工具调用 section
- 子体任务 section
- 审批中心 section
- 节点状态 section
- 执行时间线 section
- 输入框顶部的说明标签

### 2. 顶部轻量运行头

顶部运行头只保留当前会话级强信号：

- 当前会话 key
- 当前 run 状态
- 运行中子智能体数量
- 停止当前 run 的入口

这里不承担详细过程展示，不承担工具统计明细，也不承担节点监控。

### 3. 统一 transcript

中间主区域成为唯一主舞台。所有运行过程都以消息块形式插入其中。

新的 transcript 不再只消费简单 `ChatMessage[]`，而是消费规范化后的 block 列表。

## 消息块模型

### 1. 顶层 block 类型

AuraEve 聊天页需要新增统一 block 类型模型，至少包含：

- user
- assistant_text
- run_status
- tool_group
- tool_call
- tool_result
- agent_task
- agent_result
- system_notice
- collapsed_activity

### 2. 各 block 的职责

`user`

- 展示用户输入
- 保留当前 AuraEve 用户气泡风格

`assistant_text`

- 展示最终回复或阶段性解释
- 支持 Markdown 渲染
- 是用户理解结果的主入口

`run_status`

- 展示本轮运行的重要状态切换
- 例如：开始分析、开始拆解、正在汇总、已结束

`tool_call`

- 展示某个高价值工具调用
- 默认只显示动作摘要、状态、可选简短标签
- 不默认展开原始参数

`tool_result`

- 展示某个工具结果的摘要
- 默认不输出完整原始数据
- 出错时提升可见性

`tool_group`

- 用于表示一组可并列展示的同类工具活动
- 只在确实有分组收益时使用

`agent_task`

- 展示子智能体启动、运行中、暂停、完成、失败
- 折叠态显示名称、目标、状态、耗时、工具数
- 支持展开完整子 transcript

`agent_result`

- 展示子智能体完成后的结果摘要
- 与 `agent_task` 绑定

`system_notice`

- 展示错误、中止、run 完成等强系统信号
- 只保留用户真正需要感知的系统状态

`collapsed_activity`

- 折叠连续的 search/read/list/bash-readonly 活动
- 例如：搜索 6 次，读取 12 个文件
- 支持展开查看内部条目

### 3. 不再保留的类型

以下聊天页能力不纳入新的 block 模型：

- approval_request
- approval_result
- node_status_panel
- timeline_panel
- approvals summary

原因是当前通用智能体场景不需要审批流程，节点与时间线也不应常驻主阅读路径。

## 折叠与展开规则

### 1. 默认折叠规则

连续出现的以下活动需要自动折叠：

- 文件读取
- 文本搜索
- 目录列表
- 只读 Bash 命令
- 子智能体内部的低价值搜索/读取过程

折叠后的摘要需要显示：

- 活动类别计数
- 最近一个可读提示
- 当前是否仍在进行

### 2. 自动展开规则

以下内容默认不折叠：

- 用户消息
- assistant 最终回复
- 工具失败
- 子智能体失败
- run 中止
- 系统错误

### 3. 手动展开规则

用户可以手动展开：

- 某个工具块
- 某个折叠活动组
- 某个子智能体块

展开行为要求：

- 展开只影响当前 block
- 不跳转页面
- 不改变其他 block 的折叠状态
- 子智能体展开后展示完整子 transcript

## 子智能体展示设计

### 1. 折叠态

子智能体折叠态至少显示：

- 子智能体名称或角色
- 本次目标
- 当前状态
- 已耗时
- 工具调用数量

### 2. 展开态

子智能体展开后展示自己的 transcript，使用同一套 block 类型：

- assistant_text
- tool_call
- tool_result
- collapsed_activity
- system_notice

不再额外发明“子智能体日志视图”。

### 3. 结果回流

子智能体完成后，其结果需要在主线程 transcript 中体现为：

- 一个 `agent_result` 摘要块
- 随后由主 assistant 继续生成汇总回复

这样主线可以明确表达“子体完成了什么”和“主智能体如何吸收结果”。

## 后端事件与接口设计

### 1. 当前问题

当前后端事件过粗，只能表达：

- chat.started
- chat.final
- chat.error
- chat.aborted

这不足以支撑 Claude Code 式的过程展示。

### 2. 目标事件流

聊天页需要改成统一 transcript 事件流。建议新增或重构为以下事件：

- run.started
- assistant.delta
- assistant.final
- tool.started
- tool.updated
- tool.finished
- agent.started
- agent.updated
- agent.finished
- system.notice
- run.finished
- run.aborted

### 3. 历史接口

历史接口不再只返回简单 `messages`，而应返回规范化后的 transcript blocks：

- 按渲染顺序返回
- 每个 block 具有稳定 id
- 每个 block 具备 type、status、summary、details 等字段

前端不再从 `history + runtime snapshot` 生拼 UI，而是直接渲染后端组织好的 block 流。

### 4. 实时接口

SSE 需要推送增量 block 事件，而不是只推最终文本。

要求：

- 每个实时事件都能映射到某个 block 的创建或更新
- 前端可以增量更新某个 block 的状态
- 子智能体和工具事件都必须携带稳定关联 id

### 5. 运行快照接口

若保留快照接口，其职责应缩小为：

- 页面初始恢复
- 刷新后重建当前 transcript 状态

快照接口不再服务于右侧控制台聚合，也不再承担多 section 面板的数据来源。

## 前端组件边界

### 1. 页面层

`ChatPage`

- 负责页面骨架
- 订阅 transcript 数据
- 管理 run 状态与 composer

### 2. Transcript 层

新增 transcript 渲染组件，职责包括：

- block 列表渲染
- 自动滚动到底部
- 折叠与展开状态管理
- 运行中 block 的增量更新

### 3. Block 组件层

按 block 类型拆分组件，例如：

- UserBlock
- AssistantTextBlock
- ToolCallBlock
- ToolResultBlock
- AgentTaskBlock
- CollapsedActivityBlock
- SystemNoticeBlock

### 4. 数据适配层

新增前端适配层，将后端事件或历史 block 数据投影为前端渲染模型。

此层负责：

- block 去重
- 状态更新
- 增量 patch
- 展开态关联

## 视觉约束

本次对齐只对齐信息结构，不对齐终端外观。

必须保留：

- AuraEve 当前 WebUI 主题
- 配色变量
- 玻璃态背景
- 现有页面外壳
- 现有视觉风格中的圆角、层次和阴影体系

允许变化：

- 聊天页内部布局
- 消息块样式层次
- transcript 中的块状排布方式
- 工具与子智能体的展示组件

## 兼容性要求

- 已有会话历史在没有新 block 数据时，允许使用一次性投影规则回填为基础 transcript
- 新实时事件模型上线后，历史和实时都必须收敛到同一 block 模型
- 不再为聊天页保留右侧控制台兼容模式

## 风险与约束

### 1. 风险

- 后端事件模型改动较大，影响前后端同步节奏
- 历史数据如果仍是简单 message 结构，初期需要投影层过渡
- 子智能体过程如果没有稳定事件 id，会导致展开态和增量更新难以一致

### 2. 关键约束

- 不能为了兼容旧页面而保留双栏主结构
- 不能把所有 runtime 信息重新塞回顶部状态区
- 不能让节点状态、审批、时间线重新成为首屏核心信息

## 验收标准

完成后，聊天页应满足以下判断标准：

- 用户不需要看右侧控制台，也能理解智能体正在做什么
- 工具调用和子智能体过程能在主消息流中清晰追踪
- 连续搜索与读取不会刷屏
- 子智能体可以展开查看完整过程
- 聊天页首页不再出现审批、节点、时间线等当前场景无用信息
- 视觉风格仍然明显属于 AuraEve，而不是终端 UI 的照搬

## 文件级影响范围

本设计预期会影响以下区域：

- `webui/src/pages/ChatPage.tsx`
- `webui/src/components/chat/ChatComposer.tsx`
- `webui/src/components/chat/ChatMessageBubble.tsx`
- 新增 transcript 相关组件目录
- `webui/src/api/client.ts`
- `auraeve/webui/chat_service.py`
- `auraeve/webui/chat_console_service.py`
- `auraeve/webui/server.py`
- 聊天页相关 schema 定义

## 结论

AuraEve 聊天页的这次重构，本质上不是一次样式优化，而是一次展示模型切换：

- 从“聊天框 + 运行控制台”
- 切换为“统一 transcript 驱动的运行界面”

这也是与 Claude Code 对齐的关键。只要消息块模型、折叠规则、子智能体展开机制和后端事件流真正对齐，AuraEve 即使保留自己的 WebUI 主题，也能获得与 Claude Code 相同的信息清晰度。
