# 工具速查

仅保留高频、易错、能明显提升效率的用法。系统实际可用工具以当轮提示词中的工具目录为准；这里不重复完整参数说明。

## 使用原则

- 低风险操作直接执行：读文件、搜索、列目录、抓取网页
- 高风险操作先一句话说明：覆盖、批量改动、对外发送、改系统配置
- 有专用工具时优先用专用工具；不要先写脚本绕路
- 外部信息优先顺序：MCP / 技能 > 已知来源抓取 > `web_search`
- 只读且互不依赖的调用才并发；依赖前一步结果时必须串行
- 不凭印象回答；先读文件、查资料、跑命令确认事实
- 复杂任务先建计划；开放式信息收集优先交给同步子智能体扩散处理，再由主线程综合

## 高效组合

### 搜索定位

- 按路径找文件：`Glob`
- 按内容找位置：`Grep`
- 确认上下文：`Read`

```python
Glob(pattern="**/*.py", path="D:/repo")
Grep(pattern="build_system_prompt", path="D:/repo/auraeve", output_mode="content")
Read(file_path="D:/repo/auraeve/agent/context.py")
```

### 修改文件

- 改已有文件前先完整 `Read`
- 小范围改动优先 `Edit`
- 需要整文件重写时再 `Write`

```python
Read(file_path="D:/repo/workspace/TOOLS.md")
Edit(
  file_path="D:/repo/workspace/TOOLS.md",
  old_string="旧内容",
  new_string="新内容"
)
```

### 需要额外证据时

- 文件证据不够时，用 `Bash` 跑测试、构建、git、系统检查
- 能用结构化工具完成时，别用 `Bash` 代替 `Read/Grep/Glob`
- 外部资料若已有 MCP 或技能可直达，优先用它们；不要先上通用搜索
- 已知官方文档、指定网页、明确 URL，优先 `web_fetch`
- 只有 MCP、技能、已知来源都不满足，且确实需要最新外部信息时，再用 `web_search`
- `web_search` 有成本；不要频繁小搜，优先一次查询带全主体、关键词、时间范围，尽量一轮拿够信息

```python
Bash(command="pytest tests/test_task_mode_and_tools.py", timeout=600000)
```

## 子智能体

### 适合派发的场景

- 开放式调研、需要多角度并行搜索
- 主线程需要尽快拿到研究结果来做下一步判断
- 你不想自己串行调用大量工具做发散式收集
- 实现、验证、调研可以拆成互不冲突的子任务

### 使用规则

- 默认优先考虑 `execution_mode="sync"` 做前台研究收集；主线程拿到结果后再综合决策
- 只有主线程还有独立工作可并行推进时，再用后台 `async`
- 当前上下文已经很丰富，且希望子智能体继承它时，用 `fork`
- 子智能体 prompt 必须自包含，不要假设它看得到主对话
- 写清目标、范围、相关文件、禁止事项、完成标准
- 只读调研任务要明确写 `不要修改文件`
- 写任务按文件或模块拆开，避免多个子智能体改同一片区域
- 调研完成后，先由主线程综合结果，再决定继续同一个子智能体还是新开一个

### 推荐心法

- 自己调工具，适合已知路径、已知目标、收敛型任务
- 同步子智能体，适合未知范围、需要扩散搜索、需要它先帮你做一轮信息收集
- 主线程负责综合，不把“基于你的发现继续做”这种懒委托再丢回去

### 示例：并发调研

```python
agent(
  action="spawn",
  subagent_type="explore",
  execution_mode="sync",
  prompt="调查 auraeve/agent_runtime/ 中与 prompt 组装相关的实现。重点看 PromptAssembler、ContextBuilder、工具注入路径。报告关键文件、函数、调用链。不要修改文件。"
)
agent(
  action="spawn",
  subagent_type="explore",
  execution_mode="sync",
  prompt="调查 workspace/ 下的 AGENTS.md、TOOLS.md、USER.md 在运行时如何进入系统提示词。给出关键文件和结论。不要修改文件。"
)
```

### 示例：主线程综合后继续实现

```python
agent(
  action="continue",
  task_id="agent-123",
  prompt="根据你刚才报告的结论，修改 auraeve/agent/context.py 的子智能体使用规范。把“优先 sync 做前台研究、async 只用于有独立并行工作、fork 用于继承上下文”写清楚。改完后报告修改点。"
)
```

### 示例：独立验证

```python
agent(
  action="spawn",
  subagent_type="verifier",
  execution_mode="sync",
  prompt="验证最近对 TOOLS.md 的修改是否与当前 agent 工具行为一致。重点检查 sync/async/fork 的描述是否准确，是否过度鼓励主线程自己调用工具做发散搜索。只读检查，不要修改文件。输出发现的问题和改进建议。"
)
```

## 常见模式

- 用户要“先帮我把相关实现都摸清楚”：优先 `agent(sync, explore)`，再由主线程综合
- 用户要“看看某个已知位置怎么实现的”：`Glob/Grep/Read`
- 用户要“直接改掉”：`Read -> Edit/Write -> Bash 验证`
- 用户要“查外部资料”：优先 MCP/技能，其次 `web_fetch` 已知来源，最后才 `web_search`
- 用户要“发文件给我”：先拿到绝对路径，再 `message`
