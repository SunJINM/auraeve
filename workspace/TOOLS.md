# 可用工具

本文档描述 AuraEve 当前工作区常用工具的使用方式。系统实际可用工具以当轮提示词中的工具目录为准；本文件提供更具体的行为建议、边界和示例。

## 使用原则

- 低风险操作直接执行：读文件、搜索、读取网页内容
- 高风险操作先简短说明：删除、覆盖、批量改动、对外发送、改系统配置
- 有专用工具时优先用专用工具；没有合适工具时，再写脚本
- 多个互不依赖的操作尽量并行，减少轮次和等待
- 不凭印象回答；先读文件、查资料、跑命令确认事实

## 文件操作

### Read
读取文件内容。
```
Read(file_path: str, offset: int = 1, limit: int = None) -> str
```

### Write
创建或覆盖文件内容；如需要会自动创建父目录。
```
Write(file_path: str, content: str) -> str
```

### Edit
通过替换特定文本精确编辑文件。
```
Edit(file_path: str, old_string: str, new_string: str, replace_all: bool = false) -> str
```

## Shell 执行

### Bash
执行 Bash Shell 命令并返回结果。
```
Bash(
  command: str,
  timeout: int = None,
  description: str = None,
  run_in_background: bool = False,
  dangerouslyDisableSandbox: bool = False
) -> str
```

**说明：**
- Windows 上使用 Git Bash 运行
- 命令有超时限制（毫秒）
- 明显危险的命令会被拦截
- 可以用 `run_in_background=true` 启动后台任务
- 当前工作目录会在同一轮工具调用内持续跟踪

## 脚本策略

当现有工具不能直接完成任务时，写脚本是标准手段，但不是默认第一选择。

**优先顺序：**
1. 先看是否已有专用工具可直接完成
2. 专用工具不合适时，再写脚本
3. 脚本执行后读取输出，再决定下一步

**推荐做法：**
1. 用 `Write` 将脚本写到当前工作区的 `scripts/`
2. 用 `Bash` 执行脚本
3. 读取输出并继续处理

**示例 1：处理 JSON 数据**
```python
# Write("scripts/parse_data.py", ...)
import json

data = json.load(open("data.json", "r", encoding="utf-8"))
result = [item for item in data if item["status"] == "active"]
print(json.dumps(result, ensure_ascii=False, indent=2))
```
```python
Bash(command="python scripts/parse_data.py")
```

**示例 2：多步 API 调用**
```python
# Write("scripts/fetch_weather.py", ...)
import json
import urllib.request

url = "https://wttr.in/Beijing?format=j1"
res = urllib.request.urlopen(url)
data = json.loads(res.read())
print(data["current_condition"][0]["weatherDesc"][0]["value"])
```
```python
Bash(command="python scripts/fetch_weather.py")
```

**示例 3：批量文件处理**
```python
# Write("scripts/rename_files.py", ...)
import re
from pathlib import Path

for f in Path("data").glob("*.txt"):
    new_name = re.sub(r"\s+", "_", f.stem) + f.suffix
    f.rename(f.parent / new_name)
    print(f"{f.name} -> {new_name}")
```
```python
Bash(command="python scripts/rename_files.py")
```

**适合写脚本的场景：**
- 数据处理
- 批量操作
- 格式转换
- 复杂计算
- 多步 API 调用

**不适合写脚本的场景：**
- 已有专用工具可以直接完成
- 只是一次读取、一次搜索、一次发送

## 网络访问

### web_search
搜索网络信息。
```
web_search(query: str, count: int = 5) -> str
```

### web_fetch
抓取并提取网页主要内容。
```
web_fetch(url: str, extractMode: str = "markdown", maxChars: int = 50000) -> str
```

**建议：**
- 先用 `web_search` 找来源，再用 `web_fetch` 读具体页面
- 搜索时尽量带上关键词、时间范围、主体名
- 需要给用户可核实的信息时，保留来源链接

## 浏览器

### browser
浏览器自动化工具，支持打开网页、交互、快照、截图、保存 PDF。
```
browser(action: str, ...)
```

常见操作：
- `navigate`：打开网页
- `act`：点击、输入、选择、按键等
- `snapshot`：读取页面内容快照
- `screenshot`：截图并保存到本地
- `pdf_save`：将页面保存为 PDF
- `close`：关闭浏览器

## 记忆检索

### memory_search
搜索长期记忆和历史记录。
```
memory_search(query: str, max_results: int = 8, min_score: float = 0.05) -> str
```

### memory_get
读取指定记忆文件的精确片段。

### memory_status
查看记忆索引状态和检索模式。

**建议：**
- 回答历史决策、偏好、日期、人物、待办事项前，先用 `memory_search`
- 需要精确引用时，再用 `memory_get`

## 消息发送

### message
向用户发送消息，支持文字、本地文件和公开图片 URL。
```
message(
  content: str,
  file_path: str = None,
  image_url: str = None,
  channel: str = None,
  chat_id: str = None
) -> str
```

**使用规则：**
- 发送文件：`message(content="", file_path="/绝对路径/文件名")`
- 发送图片 URL：`message(content="", image_url="https://...")`
- 同时发文字和文件时，传 `content + file_path`
- `content` 可以为空字符串，但参数本身必须传

**回复规则：**
- 如果 `message` 已经完成了全部用户可见交付，且不需要额外说明，最终回复可用 `__SILENT__`
- 如果用户还需要结论、提醒或说明，发送完 `message` 后仍应正常回复

**典型用法：**
```python
message(content="", file_path="D:/reports/summary.pdf")
message(content="天气图：", image_url="https://example.com/weather.png")
message(content="分析完毕，附上报告。", file_path="D:/reports/output.xlsx")
```

**重要：**
- 用户说“发文件给我”“发图片给我”时，先找路径，再调用 `message`
- 不要说“无法发送文件”；这是已支持能力
- 需要发给其他渠道或其他会话时，明确传 `channel` 和 `chat_id`

## 子智能体

### agent
启动或管理后台子智能体任务。
```
agent(
  action: str = "spawn",
  prompt: str = None,
  subagent_type: str = "general-purpose",
  run_in_background: bool = True,
  role_prompt: str = None,
  max_steps: int = 50,
  max_tool_calls: int = 100,
  task_id: str = None
) -> str
```

**action 可选值：**
- `spawn`：创建任务
- `list`：列出任务
- `status`：查看任务详情
- `cancel`：取消任务

**subagent_type 可选值：**
- `general-purpose`：通用执行
- `explore`：偏只读搜索
- `plan`：偏方案分析

**典型用法：**
```python
agent(action="spawn", prompt="搜索最新的 AI 论文并总结关键发现")
agent(action="spawn", prompt="从法律、舆情、行业三个角度分析这个问题", subagent_type="explore")
agent(action="list")
agent(action="status", task_id="abc123")
agent(action="cancel", task_id="abc123")
```

**建议：**
- 独立任务尽量并行派发
- 能直接完成的事不要派子智能体
- 子智能体的 prompt 要自包含，不要假设它能看到你的完整对话

## 任务管理

交互式会话（如 `webui`、`terminal`）优先使用 Task V2；非交互式会话可能仍提供 legacy `todo`。

### TaskCreate
创建任务项。
```
TaskCreate(subject: str, description: str, activeForm: str = None, owner: str = None, blocks: list[str] = None, blockedBy: list[str] = None, metadata: object = None) -> str
```

### TaskGet
读取单个任务详情。
```
TaskGet(taskId: str) -> str
```

### TaskUpdate
增量更新任务。
```
TaskUpdate(taskId: str, status: str = None, subject: str = None, description: str = None, activeForm: str = None, owner: str = None, blocks: list[str] = None, blockedBy: list[str] = None, metadata: object = None, deleted: bool = False) -> str
```

### TaskList
列出当前任务列表。
```
TaskList() -> str
```

**Task V2 建议：**
- 复杂任务开始时先拆出清晰任务项
- 开始某项前用 `TaskUpdate(..., status=\"in_progress\")`
- 完成后立刻改成 `completed`
- 修改前先用 `TaskGet` 读取最新状态
- 完成一个任务后用 `TaskList` 查看下一个任务

### todo
管理当前会话的任务规划列表（legacy，全量替换）。
```
todo(todos: list[object]) -> str
```

**legacy todo 建议：**
- 仅在未提供 Task V2 时使用
- 同一时刻只保留一个 `in_progress`
- 所有步骤完成后传空列表 `[]` 清空计划

## 定时任务

### cron
管理提醒和周期性任务。
```
cron(action: str, ...)
```

**action 可选值：**
- `status`
- `list`
- `add`
- `update`
- `remove`
- `run`
- `runs`
- `wake`

**典型用法：**
```python
cron(action="add", message="早上好", cron_expr="0 9 * * *")
cron(action="add", message="喝水", every_seconds=7200)
cron(action="add", message="会议马上开始", at="2026-04-03T15:00:00")
cron(action="list")
cron(action="remove", job_id="abc123")
```

## 心跳任务

工作区中的 `HEARTBEAT.md` 会被系统定期检查。
需要定期跟进的事项，直接维护在该文件中。

**典型用法：**
```python
Edit(
    file_path="HEARTBEAT.md",
    old_string="## 待执行任务",
    new_string="## 待执行任务\n\n- [ ] 每周一检查未完成事项并提醒"
)
```

## 添加自定义工具

如需扩展工具：
1. 在 `auraeve/agent/tools/` 中创建继承 `Tool` 的类
2. 实现 `name`、`description`、`parameters` 和 `execute`
3. 在 `auraeve/agent/tools/assembler.py` 的 `build_tool_registry()` 中注册
