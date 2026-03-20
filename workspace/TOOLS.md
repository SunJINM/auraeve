# 可用工具

本文档描述 auraeve 可用的工具。

## 文件操作

### read_file
读取文件内容。
```
read_file(path: str) -> str
```

### write_file
将内容写入文件（如需要会自动创建父目录）。
```
write_file(path: str, content: str) -> str
```

### edit_file
通过替换特定文本来编辑文件。
```
edit_file(path: str, old_text: str, new_text: str) -> str
```

### list_dir
列出目录内容。
```
list_dir(path: str) -> str
```

## 服务管理

## Shell 执行

### exec
执行 Shell 命令并返回输出。
```
exec(command: str, working_dir: str = None) -> str
```

**安全说明：**
- 命令有可配置的超时时间（默认 60 秒）
- 危险命令被屏蔽（rm -rf、format、dd、shutdown 等）
- 输出截断至 10,000 个字符
- 可配置 `restrictToWorkspace` 限制路径范围

### 脚本策略（重要）

当现有工具无法直接完成任务时，**写脚本来解决**——这是标准方法，不是备选方案。

**步骤：**
1. 用 `write_file` 将脚本写入 `workspace/scripts/`
2. 用 `exec` 执行：`python workspace/scripts/task.py`
3. 读取输出，继续下一步

**示例 1：处理 JSON 数据**
```python
# write_file("workspace/scripts/parse_data.py", ...)
import json, sys

data = json.load(open("workspace/data.json"))
result = [item for item in data if item["status"] == "active"]
print(json.dumps(result, ensure_ascii=False, indent=2))
```
```
exec("python workspace/scripts/parse_data.py")
```

**示例 2：调用第三方 API**
```python
# write_file("workspace/scripts/fetch_weather.py", ...)
import urllib.request, json

url = "https://wttr.in/Beijing?format=j1"
res = urllib.request.urlopen(url)
data = json.loads(res.read())
print(data["current_condition"][0]["weatherDesc"][0]["value"])
```

**示例 3：批量文件操作**
```python
# write_file("workspace/scripts/rename_files.py", ...)
import os, re
from pathlib import Path

for f in Path("workspace/data").glob("*.txt"):
    new_name = re.sub(r"\s+", "_", f.stem) + f.suffix
    f.rename(f.parent / new_name)
    print(f"重命名：{f.name} → {new_name}")
```

**注意：**
- 脚本放在 `workspace/scripts/` 统一管理
- 优先用 Python 标准库，避免不必要的 pip 安装
- 确实需要第三方包时，先 `exec("pip show xxx")` 检查是否已安装

## 网络访问

### web_search
使用 Brave Search API 搜索网络。
```
web_search(query: str, count: int = 5) -> str
```

返回含标题、URL 和摘要的搜索结果。需要在配置中设置 `tools.web.search.apiKey`。

### web_fetch
抓取并提取 URL 的主要内容。
```
web_fetch(url: str, extractMode: str = "markdown", maxChars: int = 50000) -> str
```

**说明：**
- 使用 readability 提取内容
- 支持 markdown 或纯文本提取
- 默认输出截断至 50,000 个字符

## 消息通信

> **原则：用工具发完消息后，最终回复必须为空字符串 `""`。**
> 系统会自动判断：若最终回复为空，则不再额外发送任何文字。
> 典型场景：发送语音、发送文件、推送图片、早安/晚安定时任务——这些已经是完整的消息，**不需要再说"已发送""完成啦"等确认文字**。

### message
向用户发送消息，支持**文字、文件附件、图片**。

```
message(
  content: str,           # 文字内容（Markdown）
  file_path: str = None,  # 本地文件绝对路径（上传后发送）
  image_url: str = None,  # 公开图片 URL（直接显示）
  channel: str = None,
  chat_id: str = None
) -> str
```

**支持的文件类型：**
- 图片：jpg / png / gif / webp
- 音频：mp3 / wav / amr
- 视频：mp4
- 文档：pdf / docx / xlsx / pptx / zip 等

**典型用法：**

发送文件（先用 exec 找到路径，再用 message 发送）：
```
exec("find /Users -name '*.pptx' 2>/dev/null | head -5")
→ 得到路径 /Users/xxx/Documents/demo.pptx
message(content="你的 PPT：", file_path="/Users/xxx/Documents/demo.pptx")
```

发文件不带说明文字：
```
message(content="", file_path="/path/to/report.pdf")
```

发网络图片：
```
message(content="天气图：", image_url="https://example.com/weather.png")
```

同时发文字 + 文件：
```
message(content="分析完毕，附上报告", file_path="/workspace/scripts/output.xlsx")
```

**重要：** 用户说"发文件给我""发图片给我"时，先用 `exec` 或 `list_dir` 找到文件路径，再用 `message(file_path=...)` 发送，**不要说"无法发送文件"**。

**给指定好友发私信（按昵称查找）：**

只知道对方昵称/备注，不知道 QQ 号时，先查好友列表再发送：
```
napcat_get_friend_list()
→ 找到"张三"对应的 user_id，例如 123456789
message(content="消息内容", channel="napcat", chat_id="private:123456789")
```

群成员同理，用 `napcat_get_group_members(group_id="群号")` 查成员列表找到 QQ 号后再发。

## 子体任务管理

### subagent
管理子体（SubAgent）的完整生命周期。子体在后台独立运行，支持本地子体和远程子体。

```
subagent(
  action: str,                  # 操作类型（见下方）
  goal: str = None,             # (spawn) 任务目标描述
  priority: int = 5,            # (spawn) 优先级 1-9
  assigned_node_id: str = "",   # (spawn) 指定执行节点 ID；留空则自动调度到最优节点
  tasks: list = None,           # (dag) DAG 任务列表
  task_id: str = None,          # 目标任务 ID
  message: str = None,          # (steer) 引导消息
  approval_id: str = None,      # (approve) 审批 ID
  decision: str = None,         # (approve) approve/reject
  limit: int = 20               # (list) 返回数量
) -> str
```

**action 可选值：**

| action | 说明 | 必填参数 |
|--------|------|----------|
| `spawn` | 派生子体在后台执行任务 | `goal` |
| `dag` | 提交 DAG 任务组（按依赖拓扑执行） | `tasks` |
| `list` | 查询任务列表 | — |
| `status` | 查询任务详情 | `task_id` |
| `steer` | 向运行中的任务推送引导消息 | `task_id`, `message` |
| `pause` | 暂停任务 | `task_id` |
| `resume` | 恢复任务 | `task_id` |
| `cancel` | 取消任务 | `task_id` |
| `approve` | 审批高风险操作 | `approval_id`, `decision` |

**典型用法：**

派生后台任务（自动调度到最优节点）：
```
subagent(action="spawn", goal="搜索最新的 AI 论文并总结关键发现")
```

派生任务到指定远程节点：
```
subagent(action="spawn", goal="检查服务器磁盘空间和内存使用情况", assigned_node_id="work-pc")
```

提交有依赖关系的 DAG 任务组：
```
subagent(action="dag", tasks=[
    {"id": "A", "goal": "收集服务器性能数据"},
    {"id": "B", "goal": "清洗并标准化数据", "depends_on": ["A"]},
    {"id": "C", "goal": "生成可视化分析报告", "depends_on": ["B"]}
])
```

查看任务状态：
```
subagent(action="list")
subagent(action="status", task_id="task-xxxx")
```

引导运行中的任务调整方向：
```
subagent(action="steer", task_id="task-xxxx", message="重点关注内存使用趋势")
```

审批子体的高风险操作请求：
```
subagent(action="approve", approval_id="apv-xxxx", decision="approve")
```

**远程节点调度：**
- 不指定 `assigned_node_id` 时，调度器根据节点能力评分、当前负载、优先级自动选择最优节点
- 指定 `assigned_node_id` 时，任务将强制分配到该节点执行
- 使用 `subagent(action="list")` 查看任务分配到了哪个节点
- 远程节点可用的工具集（read_file、write_file、list_dir、exec、web_search、web_fetch）是本地工具的安全子集

**适用场景：**
- 耗时任务（数据采集、报告生成、批量处理）
- 需要在远程节点执行的任务（如远程服务器运维、跨机器操作）
- 多步骤有依赖的工作流（DAG 编排）
- 需要并行处理的独立子任务

**风险策略：**
- 子体执行 shell 命令、文件写入等高风险操作时会自动请求审批
- 审批请求会通过消息通知，使用 `approve` action 处理

## 定时提醒（Cron）

使用 `cron` 工具直接创建定时提醒：

### 设置定期提醒
```
cron(action="add", message="早上好！☀️", cron_expr="0 9 * * *")
cron(action="add", message="喝水！💧", every_seconds=7200)
```

### 设置一次性提醒
```
cron(action="add", message="会议马上开始！", at="2025-01-31T15:00:00")
```

### 管理提醒
```
cron(action="list")              # 列出所有任务
cron(action="remove", job_id="abc123")   # 删除任务
```

## 心跳任务管理

工作区中的 `HEARTBEAT.md` 文件每 30 分钟被检查一次。
使用文件操作来管理定期任务：

### 添加心跳任务
```python
edit_file(
    path="HEARTBEAT.md",
    old_text="## 待执行任务",
    new_text="## 待执行任务

- [ ] 新定期任务"
)
```

### 删除心跳任务
```python
edit_file(
    path="HEARTBEAT.md",
    old_text="- [ ] 要删除的任务
",
    new_text=""
)
```

### 重写所有任务
```python
write_file(
    path="HEARTBEAT.md",
    content="# 心跳任务

- [ ] 任务 1
- [ ] 任务 2
"
)
```

---

## 添加自定义工具

添加自定义工具：
1. 在 `auraeve/agent/tools/` 中创建继承 `Tool` 的类
2. 实现 `name`、`description`、`parameters` 和 `execute`
3. 在 `auraeve/agent/tools/assembler.py` 的 `build_tool_registry()` 中注册
