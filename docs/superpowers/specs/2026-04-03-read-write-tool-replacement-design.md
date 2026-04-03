# AuraEve Read/Write 工具替换设计

日期: 2026-04-03
状态: 已在对话中确认方向，等待用户审阅书面设计稿

## 摘要

AuraEve 将删除当前轻量文件工具 `read_file` 与 `write_file`，改为完整引入 Claude Code 风格的 `Read` 与 `Write` 工具契约。此次改动不是简单重命名，而是一次行为级替换：

- 工具名替换为 `Read` / `Write`
- 参数接口替换为 Claude 风格
- 返回格式、读取限制、先读后写约束、文件变更检测对齐 Claude Code
- `Read` 接管文本、图片、PDF、Jupyter Notebook 的读取能力
- 所有相关提示词、前端展示、子智能体工具声明、测试与运行时状态一并改造

改造完成后，AuraEve 不再保留 `read_file` / `write_file` 兼容层。仓库中的文件读写主语义将统一为 Claude Code 风格的 `Read` / `Write`。

## 目标

- 用行为一致的 `Read` / `Write` 替换 AuraEve 当前 `read_file` / `write_file`
- 让 Agent 侧文件读取与写入语义对齐 Claude Code，而不是 AuraEve 当前的轻量 host op 包装
- 为 `Write` 增加“已有文件必须先读”的安全约束
- 为 `Write` 增加“读取后文件已被修改则拒绝覆盖”的陈旧检测
- 让 `Read` 支持 Claude Code 风格的分段读取、行号输出、图片/PDF/notebook 读取
- 同步更新系统提示词、工作区工具文档、前端 transcript、测试与子智能体工具声明

## 非目标

- 不在本次设计中同步替换 `Edit` 工具
- 不在本次设计中重做 AuraEve 整个工具执行框架
- 不要求 1:1 搬运 Claude Code 的所有内部实现细节，只要求对外行为、参数契约和关键约束对齐
- 不保留 `read_file` / `write_file` 兼容入口
- 不在本次设计中处理所有文档中的历史旧名字，只处理运行时、提示词、关键开发文档和核心测试

## 设计原则

- 行为优先于名字
- 对 Agent 暴露的契约必须稳定且清晰
- 写入前约束必须在运行时强制执行，不能只靠提示词提醒
- 现有 AuraEve 多媒体能力允许复用，但 `Read` 对外必须呈现统一入口
- 替换必须一次到位，避免同时维护两套文件读写语义

## 当前问题

AuraEve 当前 `read_file` / `write_file` 存在以下问题：

- 工具名和参数接口与 Claude Code 不一致
- `read_file` 只能整文件读取文本，不支持按行范围读取
- `read_file` 不输出行号，不利于后续 `Edit` 和代码定位
- `write_file` 不区分新建文件与覆盖已有文件的风险
- `write_file` 不要求先读取已有文件
- `write_file` 不校验“读取后文件是否被外部修改”
- 图片、PDF、notebook 读取分散在其他能力中，缺少统一的 `Read` 入口
- 提示词、前端 transcript、子智能体工具白名单都依赖旧名字

## 目标契约

### 1. 工具名

- `Read`
- `Write`

旧名 `read_file` / `write_file` 从默认工具注册中移除，不提供别名。

### 2. Read 输入契约

`Read` 对外暴露如下参数：

- `file_path`: 必填，绝对路径
- `offset`: 可选，从第几行开始读取
- `limit`: 可选，读取多少行
- `pages`: 可选，仅用于 PDF 页范围读取

### 3. Write 输入契约

`Write` 对外暴露如下参数：

- `file_path`: 必填，绝对路径
- `content`: 必填，整文件内容

### 4. Write 行为约束

- 目标文件不存在时，允许直接创建
- 目标文件已存在时，必须先通过 `Read` 成功读取该文件
- 如果先前读取的是 partial view，则禁止 `Write`
- 如果文件在读取之后被用户、格式化器或其他进程修改，则禁止 `Write`
- `Write` 是整文件重写工具，不承担局部编辑职责

## 替换后的架构

### 1. 工具层

AuraEve 将以新的 `ReadTool` / `WriteTool` 替换现有 `ReadFileTool` / `WriteFileTool`。工具名分别是 `Read` 和 `Write`，底层不再直接暴露 AuraEve 旧的 `read_file` / `write_file` 语义。

### 2. 执行层

底层执行层需要升级为 Claude 风格的文件读写执行组件，而不是当前简单的：

- 文本文件整读
- 文本文件整写

替换后执行层需要支持：

- 文本读取时按行切片
- 文本读取时生成带行号输出
- 图片读取时生成多模态可消费内容或 AuraEve provider 可接受的等价结构
- PDF 按页读取
- notebook 解析
- 写入前比对文件读取状态与文件修改时间

### 3. 运行时状态层

AuraEve 当前没有 Claude Code 风格的 `readFileState`。本次必须新增会话级文件读取状态，用于记录：

- 规范化后的绝对路径
- 最近一次成功读取时间
- 最近一次读取时文件的修改时间
- 是否是 partial view
- 读取类型（text / image / pdf / notebook）

此状态由运行时工具调用循环维护，供 `Write` 校验使用。

### 4. 提示词层

以下内容必须同步切换为 `Read` / `Write` 契约：

- `ContextBuilder` 中的工具目录说明
- 工具调用风格规则
- 技能加载指令中对 `read_file` 的引用
- 工作区 `TOOLS.md`
- 子智能体和计划类提示词中对旧工具名的引用

### 5. 前端展示层

webui transcript 需要把 `Read` / `Write` 作为一等工具名处理：

- icon 与标签改为 `Read` / `Write`
- 只读工具折叠规则纳入 `Read`
- 参数摘要从 `file_path` 读取
- 结果摘要适配新的文本/媒体读取结果

## Read 能力设计

### 1. 文本读取

`Read` 读取文本文件时：

- 默认最多读取固定上限的行数
- 支持 `offset` + `limit` 分段读取
- 返回内容必须包含行号
- 对大文件给出清晰错误或截断提示
- 对重复读取且文件未变化的情况，允许返回“文件未变化，可参考先前结果”的 stub

### 2. 图片读取

`Read` 必须能够读取本地图片路径，并将结果包装成 AuraEve provider 可理解的多模态输入结构。用户或 Agent 不需要切换到其他工具查看本地截图。

### 3. PDF 读取

`Read` 对 `.pdf` 的行为对齐 Claude：

- 小 PDF 可直接读取
- 大 PDF 必须要求指定 `pages`
- 限制单次页数
- 返回可读文本或 AuraEve 现有 PDF 抽取结果的兼容表现

### 4. Notebook 读取

`Read` 对 `.ipynb` 需要支持 notebook 级读取，返回 cell 内容与关键输出摘要，供后续 `NotebookEdit` 风格能力或 Agent 分析使用。

### 5. 路径与错误处理

- `file_path` 必须是绝对路径
- 文件不存在时返回清晰错误
- 目录路径不能被 `Read`
- 对危险设备路径、异常大输入或不支持内容类型做显式拒绝

## Write 能力设计

### 1. 新建文件

当目标文件不存在时：

- 自动创建父目录
- 写入完整内容
- 返回创建成功信息与结构化差异摘要

### 2. 覆盖已有文件

当目标文件存在时：

- 必须检查当前会话是否用 `Read` 成功读取过该文件
- 若没有读过，报错并要求先读取
- 若上次读取是 partial view，报错并要求完整读取
- 若文件自读取后发生变化，报错并要求重新读取
- 校验通过后再执行整文件覆盖

### 3. 与 Edit 的边界

- `Write` 只用于新建文件或完整重写
- 修改已有文件时，默认应优先使用 `Edit`
- 但当用户明确要求整文件改写，或生成全新内容替换时，允许用 `Write`

### 4. 输出

`Write` 的结果至少要包含：

- 本次是 `create` 还是 `update`
- 写入路径
- 写入后的内容
- 原始文件内容（若存在）
- 结构化 patch 或 AuraEve 可展示的等价 diff

## 运行时改造

### 1. 文件读取状态缓存

需要在运行时引入会话级文件读取状态表，挂在当前尝试上下文中，而不是散落在工具内部。

该状态至少支持：

- `Read` 成功后更新
- `Write` 校验时读取
- 文件写入成功后刷新状态
- transcript 或后续工具需要时可复用

### 2. 工具调用上下文

AuraEve 当前 `ToolRegistry.execute()` 只传工具参数。为了支持 Claude 风格约束，需要在工具执行层或运行时上下文中提供额外状态注入能力，使 `Read` / `Write` 能访问当前会话的文件读取状态。

### 3. 向后兼容策略

本次不提供用户侧兼容。代码层需要一次性完成仓库内核心调用点替换，使系统提示词和前端只认识 `Read` / `Write`。

## 受影响模块

以下模块预期会改动：

- `auraeve/agent/tools/filesystem.py`
- `auraeve/execution/host_ops.py`
- `auraeve/execution/dispatcher.py`
- `auraeve/agent_runtime/session_attempt.py`
- `auraeve/agent/tools/assembler.py`
- `auraeve/agent/context.py`
- `auraeve/agent/agents/definitions.py`
- `workspace/TOOLS.md`
- `webui/src/components/chat/transcript/...`
- 与文件工具相关的测试文件

若 AuraEve 现有多媒体/PDF/notebook 解析实现可复用，应优先复用已有能力，而不是复制一份完全独立的解析逻辑。

## 测试设计

本次替换至少需要覆盖以下测试：

- `Read` 文本整读
- `Read` 文本分段读取
- `Read` 行号输出格式
- `Read` 对目录/不存在文件/非法路径的错误
- `Read` 图片读取
- `Read` PDF 页范围读取
- `Read` notebook 读取
- `Write` 新建文件
- `Write` 已有文件未先读时报错
- `Write` partial read 后写入时报错
- `Write` 读取后文件被外部修改时报错
- 工具注册表只暴露 `Read` / `Write`，不再暴露旧名字
- `ContextBuilder`、`TOOLS.md`、前端 transcript 的工具名更新

## 风险与缓解

### 1. Read 过重

把文本、图片、PDF、notebook 都并入 `Read` 会提高复杂度。

缓解方式：

- 复用 AuraEve 现有 `pdf`、媒体、notebook 解析能力
- 在工具层统一入口，在内部按文件类型分发

### 2. 运行时状态接入成本

`Write` 的先读后写语义依赖新的会话状态。

缓解方式：

- 先在运行时补齐最小 `read state`
- 只为 `Read` / `Write` 提供必要上下文，不顺带重构整个工具框架

### 3. 仓库内旧名字残留

如果只改工具实现，不改提示词和前端，Agent 仍可能继续调用旧名。

缓解方式：

- 本次作为一次完整替换执行
- 将系统提示词、工具文档、前端映射、测试同步修改

## 结论

本次工作应被视为“以 Claude Code 风格完整替换 AuraEve 文件读写工具”，而不是“为旧工具补几个参数”。实现完成后：

- AuraEve 默认文件读取入口统一为 `Read`
- AuraEve 默认文件写入入口统一为 `Write`
- 旧工具名退出主运行路径
- Agent 获得与 Claude Code 接近的文件读写行为和安全边界

后续实现阶段应按测试先行推进，先建立 `Read` / `Write` 的失败测试，再逐步补齐执行层、运行时状态、提示词和前端适配。
