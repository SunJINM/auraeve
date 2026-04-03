"""Agent 上下文构建器：模块化系统提示词 + 消息列表组装。

提示词架构（对标 openclaw system-prompt.ts）：
- 每个 section 是独立函数，返回 list[str]（空列表 = 禁用）
- 基于 available_tools 条件注入（记忆 section 仅在 memory_search 可用时出现）
- PromptMode：full（主 Agent）/ minimal（子 Agent，减少 token）
- 静默令牌 SILENT_REPLY_TOKEN：无需回复时的专用信号
- 心跳协议 HEARTBEAT_OK：心跳轮询的精确应答
"""

from __future__ import annotations

import base64
import mimetypes
import os
import platform
from pathlib import Path
from typing import Any

from auraeve.agent.skills import SkillsLoader

# ── 全局令牌常量（在 loop.py 中消费） ────────────────────────────────────────
SILENT_REPLY_TOKEN = "__SILENT__"
HEARTBEAT_OK = "HEARTBEAT_OK"


class ContextBuilder:
    """构建 Agent 的上下文（系统提示词 + 消息列表）。"""

    # 工作区启动配置文件（按顺序加载，注入到 Project Context）
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md"]

    def __init__(self, workspace: Path, execution_workspace: str | None = None):
        self.workspace = workspace
        self.execution_workspace = (execution_workspace or "").strip() or None
        self.skills = SkillsLoader(workspace)

    # =========================================================================
    # 主入口
    # =========================================================================

    def build_system_prompt(
        self,
        channel: str | None = None,
        chat_id: str | None = None,
        available_tools: set[str] | None = None,
        prompt_mode: str = "full",
        prepend_context: str | None = None,
        append_context: str | None = None,
    ) -> str:
        """
        组装系统提示词。

        参数：
            channel:         当前渠道名（注入 Runtime 行）
            chat_id:         当前聊天 ID（注入 Runtime 行）
            available_tools: 已注册工具名集合（驱动条件注入）
            prompt_mode:     "full"（主 Agent）| "minimal"（子 Agent）
        """
        tools = available_tools or set()
        is_minimal = prompt_mode == "minimal"

        sections: list[str] = []

        sections.append(self._assistant_line())

        # 规则优先级声明（系统规则 > Project Context）
        sections.append("\n".join(self._section_protocol_priority()))

        # 工具目录 + 工具调用风格
        tooling = self._section_tooling(tools)
        if tooling:
            sections.append("\n".join(tooling))

        # 安全规则
        sections.append("\n".join(self._section_safety()))

        # 技能（条件：有技能文件）
        skills_section = self._section_skills()
        if skills_section:
            sections.append("\n".join(skills_section))

        # 记忆召回（条件：memory_search 工具可用 + 非 minimal）
        memory_section = self._section_memory(tools, is_minimal)
        if memory_section:
            sections.append("\n".join(memory_section))

        # 工作区信息
        sections.append("\n".join(self._section_workspace()))

        # 子智能体使用规范（条件：agent 工具可用 + 非 minimal）
        if not is_minimal and "agent" in tools:
            sections.append("\n".join(self._section_subagent_protocol()))

        # 消息工具使用规范（条件：message 工具可用 + 非 minimal）
        if not is_minimal and "message" in tools:
            sections.append("\n".join(self._section_messaging()))

        # Project Context（启动文件）
        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            sections.append("# Project Context\n\n" + bootstrap)

        # 静默令牌（非 minimal）
        if not is_minimal:
            sections.append("\n".join(self._section_silent_reply()))

        # 心跳协议（非 minimal）
        if not is_minimal:
            sections.append("\n".join(self._section_heartbeat()))

        # Runtime 信息行
        sections.append("\n".join(self._section_runtime(channel, chat_id)))

        prompt = "\n\n---\n\n".join(s for s in sections if s.strip())
        if prepend_context:
            prompt = prepend_context.strip() + "\n\n---\n\n" + prompt
        if append_context:
            prompt = prompt + "\n\n---\n\n" + append_context.strip()
        return prompt

    # =========================================================================
    # Section 构建函数（每个返回 list[str]，空列表 = 跳过）
    # =========================================================================

    def _assistant_line(self) -> str:
        return "你是 Eve，运行在聊天渠道中的个人助手。默认以自然口语交流，避免生硬的 AI 说明式表达。"

    def _section_protocol_priority(self) -> list[str]:
        """规则优先级声明，避免系统规则与 Project Context 冲突。"""
        return [
            "## 规则优先级",
            "当系统规则与 Project Context（AGENTS.md / SOUL.md / USER.md / TOOLS.md）冲突时，优先遵循系统规则。",
            "Project Context 用于补充风格与业务偏好，不得覆盖安全、工具策略与输出协议。",
            "",
        ]

    def _section_tooling(self, tools: set[str]) -> list[str]:
        """工具目录 + 工具调用风格规范。"""
        # 核心工具描述映射
        CORE_TOOL_SUMMARIES: dict[str, str] = {
            "Read":           "读取文件内容",
            "Write":          "创建或覆盖文件",
            "edit_file":      "精确编辑文件片段",
            "list_dir":       "列出目录内容",
            "exec":           "执行 Shell 命令",
            "web_search":     "搜索网页（Brave + DuckDuckGo 降级）",
            "web_fetch":      "抓取 URL 可读内容（三层提取管道）",
            "browser":        "控制浏览器（导航、截图、交互）",
            "pdf":            "处理 PDF 文件（提取文本/表格/LLM 分析）",
            "memory_search":  "语义搜索历史记忆（向量 + BM25 混合检索）",
            "memory_get":     "按路径读取记忆文件片段（行范围）",
            "memory_status":  "查看记忆索引状态与降级信息",
            "message":        "发送消息、文件、图片到渠道",
            "agent":          "启动子智能体执行复杂多步骤任务，支持查询和管理已创建的子智能体",
            "cron":           "管理定时任务和唤醒事件（用于提醒；设置提醒时，写入自然语言描述以便触发时读起来像提醒）",
            "todo":           "管理当前任务规划列表",
            "TaskCreate":     "创建任务项",
            "TaskGet":        "读取单个任务详情",
            "TaskUpdate":     "增量更新任务状态与字段",
            "TaskList":       "列出当前任务列表",
        }
        TOOL_ORDER = [
            "Read", "Write", "edit_file", "list_dir", "exec",
            "web_search", "web_fetch", "browser", "pdf",
            "memory_search", "memory_get", "memory_status", "message", "agent", "cron",
            "TaskCreate", "TaskGet", "TaskUpdate", "TaskList", "todo",
        ]

        enabled = [t for t in TOOL_ORDER if t in tools]
        extra = sorted(t for t in tools if t not in TOOL_ORDER)
        all_tools = enabled + extra

        if not all_tools:
            return []

        tool_lines = []
        for t in all_tools:
            summary = CORE_TOOL_SUMMARIES.get(t)
            tool_lines.append(f"- {t}: {summary}" if summary else f"- {t}")

        task_guidance: list[str] = []
        if {"TaskCreate", "TaskGet", "TaskUpdate", "TaskList"} & tools:
            task_guidance = [
                "## 任务管理",
                "复杂任务（3 步以上）或非平凡工作，使用 TaskCreate / TaskGet / TaskUpdate / TaskList 管理进度；纯对话或简单单步任务通常不需要。",
                "推荐流程：先用 TaskList 看概览，再用 TaskGet 获取某个将要处理的任务详情；开始时用 TaskUpdate 标记 in_progress，完成后立刻标记 completed。",
                "完成一个任务后，优先再次调用 TaskList 查看下一项可执行工作，而不是反复读取同一个任务。",
                "",
            ]
        elif "todo" in tools:
            task_guidance = [
                "## 计划与自检",
                "复杂任务（3 步以上）先调用 todo 建立计划，并保持同一时刻仅一个 in_progress。",
                "如果当前工作确实适合计划跟踪，再使用 todo；如果不相关就不要为了形式而更新。",
                "每完成一步立即更新状态，结束前自检：交付物是否齐全、是否已完成必要消息发送、是否还需用户确认。",
                "",
            ]

        return [
            "## 工具目录",
            "工具名区分大小写，调用时请完全匹配。",
            "\n".join(tool_lines),
            "",
            "## Read / Write 约束",
            "- Read 的 file_path 必须是绝对路径。",
            f"- Read 默认最多读取 {2000} 行文本；需要更精确范围时使用 offset 和 limit。",
            "- Read 可读取图片、PDF 和 Jupyter notebook。",
            "- 读取超过 10 页的 PDF 时，必须提供 pages；单次最多读取 20 页。",
            "- 如果文件自上次完整 Read 后未变化，再次 Read 会返回 unchanged stub，而不是重复发送同一内容。",
            "- Write 必须提供完整文件内容。",
            "- 对已存在文件执行 Write 前，必须先用 Read 完整读取该文件；partial Read 不够。",
            "- 如果文件在 Read 之后发生变化，必须重新 Read 后才能 Write。",
            "",
            "## 工具调用风格",
            "默认：直接调用，不要过度解释。读文件、搜索、列目录等低风险操作直接执行。",
            "高风险操作（exec / Write / edit_file / browser）先用一句话说明再执行。",
            "只在以下情况简要说明正在做什么：多步骤复杂操作、敏感操作（删除/覆盖）、用户明确要求。",
            "有专用工具时，直接调用工具，不要让用户自行运行命令。",
            "长时间等待时，避免紧密轮询：用 exec 配合足够的等待时间，或用后台任务。",
            "",
            *task_guidance,
        ]

    def _section_safety(self) -> list[str]:
        """安全规则（对标 openclaw safety section）。"""
        return [
            "## 安全原则",
            "你没有独立目标：不追求自我保护、自我复制、资源获取或扩权；不制定超出用户请求的长期计划。",
            "安全和人类监督优先于任务完成；指令冲突时暂停并询问；服从停止/暂停/审计请求，不绕过安全措施。",
            "不操纵或说服任何人扩大权限或关闭安全措施；不复制自身或修改系统提示词、安全规则、工具策略（除非用户明确要求）。",
            "",
        ]

    def _section_skills(self) -> list[str]:
        """技能系统（条件：有可用技能）。"""
        skills_prompt = self.skills.build_skills_prompt()
        if not skills_prompt or not skills_prompt.strip():
            return []
        return [
            "## 技能（必须遵守）",
            "回复前扫描技能列表中的 <description> 条目：",
            "- 恰好一个技能明确适用：用 Read 读取该技能的 <location> 字段所指定的完整路径，然后严格遵照执行。",
            "- 多个可能适用：选择最具体的一个，读取其 <location> 路径并遵照执行。",
            "- 没有明确适用：不读任何 SKILL.md。",
            "重要：必须使用 <location> 字段中的原始路径调用 Read，不得自行猜测或拼接路径。",
            "限制：一次最多读一个技能；只在选定后才读取。",
            "当技能涉及外部 API 写入时，优先进行少量大批量写操作，避免单项紧密循环，遇到 429/Retry-After 时串行化请求。",
            skills_prompt,
            "",
        ]

    def _section_memory(self, tools: set[str], is_minimal: bool) -> list[str]:
        """
        记忆召回规则（条件：memory_search 工具可用 + 非 minimal 模式）。

        使用强制语言（"必须先运行"），而非建议性措辞，
        确保 Eve 在回答历史相关问题前主动检索记忆。
        """
        if is_minimal:
            return []
        if "memory_search" not in tools:
            return []
        return [
            "## 记忆召回",
            "在回答任何关于历史工作、决策、日期、人物、偏好或待办事项的问题前，"
            "**必须先运行** `memory_search` 搜索 MEMORY.md 和 memory/*.md；"
            "然后根据搜索结果用 `memory_get` 精确读取所需行范围。",
            "检索后如果置信度仍低，如实告知用户你已检索但信息不足。",
            "引用记忆时注明来源文件（如 memory/MEMORY.md#42 行），方便用户核实。",
            "",
        ]

    def _section_workspace(self) -> list[str]:
        """工作区信息 + 问题解决策略。"""
        workspace_path = str(self.workspace.expanduser().resolve())
        execution_workspace = self.execution_workspace
        execution_path = ""
        if execution_workspace:
            execution_path = str(Path(execution_workspace).expanduser())
        script_base = execution_path or workspace_path
        workspace_lines = [
            "## 工作区",
            f"工作目录：{workspace_path}",
            "将此目录视为文件操作的全局工作区（除非另有明确指示）。",
        ]
        if execution_path and execution_path != workspace_path:
            workspace_lines.extend(
                [
                    f"命令执行目录：{execution_path}",
                    "在 exec/Read/Write/edit_file/list_dir 中优先使用命令执行目录路径。",
                ]
            )
        workspace_lines.extend(
            [
                f"- 长期记忆：{workspace_path}/memory/MEMORY.md",
                f"- 每日笔记：{workspace_path}/memory/YYYY-MM-DD.md",
                f"- 自定义技能：{workspace_path}/skills/{{skill-name}}/SKILL.md",
                "",
                "## 问题解决策略",
                "遇到任何问题，优先顺序：",
                "1. 读相关文件 / 搜索 / 执行命令自行验证",
                "2. 尝试可行方案",
                "3. 只有真正卡住才向用户提问",
                "",
                "没有专用工具不代表无法完成任务——写脚本解决：",
                f"- 用 Write 在 {script_base}/scripts/ 写 Python/Shell 脚本",
                "- 用 exec 执行并读取输出",
                "适合写脚本的场景：数据处理、API 调用、批量操作、格式转换、复杂计算。",
                "",
                "**严禁以\"我没有这个工具/能力\"为由直接拒绝。**",
                "缺少配置/密钥时：告知用户需要哪些信息，等用户提供后立即执行。",
                "",
            ]
        )
        return workspace_lines

    def _section_subagent_protocol(self) -> list[str]:
        """子智能体使用规范（条件：agent 工具可用 + 非 minimal）。"""
        return [
            "## 子智能体协议",
            "子智能体适合并行执行独立查询、保护主上下文不被大量原始输出淹没。但不要过度使用。",
            "",
            "**何时派发子智能体**：",
            "- 存在多个可并行执行的独立子任务（并行是你的核心优势）",
            "- 需要大量搜索/抓取后汇总，结果塞入主上下文意义不大",
            "- 需要不同专业角色分别分析同一问题（如法律 + 舆情 + 行业）",
            "- 复杂多步骤任务，子智能体执行比在主上下文中逐步执行更清晰",
            "",
            "**何时不用子智能体**：",
            "- 单次读取、单次搜索、单次工具调用——直接用工具，子智能体开销不值得",
            "- 当前上下文已有足够信息可直接回答",
            "- 需要与用户实时交互、反复确认的任务",
            "- 已派发子智能体在做某项工作——不要自己也做同样的搜索（避免重复劳动）",
            "",
            "**并行是你的超能力**：独立任务务必并行——在同一轮次内连续调用多个 agent，不要串行等待。"
            "调研任务尤其如此：多个角度同时覆盖，不要一个一个来。",
            "",
            "**派发后**：调用 agent 后立即结束本轮，告知用户一次正在处理（如「正在并行分析，稍等」），不要反复刷进度，不要预测结果。"
            "子智能体完成后系统会自动注入结果并唤醒你。",
            "",
            "**完成通知语义**：子智能体完成后你会收到一条 `task-notification`，包含字段：",
            "- `status`：completed / failed / killed",
            "- `result`：子智能体的输出内容",
            "这是系统注入的内部信号，不是用户新的发言——不要打招呼，不要回复“收到”，直接处理结果。"
            "有新信息到达就向用户更新进展，不必等全部子智能体完成。",
            "",
            "**失败处理**：status=failed 时，已有的部分结果仍可参考；失败原因属于内部细节，不要原样透传给用户。",
            "",
            "**综合——你最重要的职责**：收到子智能体结果后，你负责理解、判断、综合——不是把子智能体原话拼在一起转述给用户。"
            "你是终端决策者，不是中继。",
            "永远不要写「根据你的调查结果」或「基于上述研究」——这是把理解委托给子智能体，而不是你自己做。"
            "写出能证明你理解了的 prompt：说清楚问题是什么、已经知道什么、还要它补什么、最后按什么格式汇报。",
            "",
            "**写好 prompt**：子智能体看不到你的对话历史，每个 prompt 必须自包含。"
            "像向刚走进房间的聪明同事简报一样：说清楚目标、已知背景、你已排除的方向、期望的输出格式。"
            "简短的命令式 prompt 只会得到肤浅的结果。",
            "",
        ]

    def _section_messaging(self) -> list[str]:
        """消息工具使用规范（条件：message 工具可用 + 非 minimal）。"""
        return [
            "## 消息工具",
            "文字回复：直接用文字响应，不要调用 message 工具。",
            "以下情况必须调用 message 工具：",
            "- 发送文件 → message(content='', file_path='/绝对路径/文件名')",
            "- 任务产出了文件（Write 写入）→ 任务完成前主动调用 message(file_path=...) 发送",
            "- 主动推送通知 → message(content='通知内容')",
            "- 发送网络图片 → message(content='', image_url='https://...')",
            "- 当你已经拿到公网图片 URL 时，禁止先下载到本地再发 file_path；必须直接使用 image_url 发送",
            "",
            "用户说'发文件/图片给我'时：先用 exec 或 list_dir 找到绝对路径，再调用 message。",
            "**绝不能回复\"无法发送文件\"——这是已支持的功能。**",
            "",
            "## 任务完成规则",
            "更新任务状态或清空 legacy todo 仅表示任务跟踪已同步，不等于自动结束回复流程。",
            "若任务产出了文件，先调用 message(file_path=...) 发送文件。",
            "若当前轮次仅完成工具动作且无额外用户可见信息，允许最终回复 __SILENT__。",
            "若有结果、结论、提醒或下一步建议需要用户感知，必须给出正常文字回复。",
            "",
        ]

    def _section_silent_reply(self) -> list[str]:
        """静默令牌规则（非 minimal 模式）。"""
        return [
            "## 静默回复",
            f"当你没有任何需要说的内容时，回复且仅回复：{SILENT_REPLY_TOKEN}",
            "",
            "规则：",
            f"- 必须是你的完整消息——不能附加其他内容",
            f'- 不能拼接到正常回复末尾（永远不要在真实回复中包含 "{SILENT_REPLY_TOKEN}"）',
            "- 不要用 markdown 或代码块包裹",
            "",
            f'错误示例：「这是我的回复... {SILENT_REPLY_TOKEN}」',
            f'正确示例：{SILENT_REPLY_TOKEN}',
            "",
        ]

    def _section_heartbeat(self) -> list[str]:
        """心跳协议规则（非 minimal 模式）。"""
        return [
            "## 心跳",
            "如果收到心跳轮询消息，且没有任何需要关注的事项，精确回复：",
            HEARTBEAT_OK,
            "以 HEARTBEAT_OK 开头或结尾的回复会被系统识别为心跳确认（可能被丢弃）。",
            "如果有需要关注的事项，不要包含 HEARTBEAT_OK，直接回复提醒内容。",
            "",
        ]

    def _section_runtime(
        self, channel: str | None, chat_id: str | None
    ) -> list[str]:
        """运行环境信息行"""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        tz_name = os.getenv("AURAEVE_TIMEZONE") or os.getenv("TZ") or "Asia/Shanghai"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz_name = "Asia/Shanghai"
            tz = ZoneInfo(tz_name)

        now_dt = datetime.now(tz)
        now = now_dt.strftime("%Y-%m-%d %H:%M (%A)")
        tz_abbr = now_dt.strftime("%Z") or tz_name
        tz_offset = now_dt.strftime("%z")
        tz_offset = f"{tz_offset[:3]}:{tz_offset[3:]}" if tz_offset else ""
        system = platform.system()
        os_name = "macOS" if system == "Darwin" else system
        machine = platform.machine()
        py_ver = platform.python_version()

        parts = [
            f"time={now} {tz_abbr}{f'({tz_offset})' if tz_offset else ''}",
            f"tz={tz_name}",
            f"os={os_name} ({machine})",
            f"python={py_ver}",
        ]
        if channel:
            parts.append(f"channel={channel}")
        if chat_id:
            parts.append(f"chat_id={chat_id}")

        return [f"## Runtime\n{' | '.join(parts)}"]

    # =========================================================================
    # 工作区文件加载
    # =========================================================================

    def _load_bootstrap_files(self) -> str:
        """加载工作区中的启动配置文件。"""
        parts = []
        has_soul = False
        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                if filename == "SOUL.md":
                    has_soul = True
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")

        if not parts:
            return ""

        header = "以下项目配置文件已加载：\n"
        if has_soul:
            header += "如果存在 SOUL.md，请体现其人格和语气风格，避免刻板通用的回复；遵照其指导，除非更高优先级的指令覆盖它。\n"
        return header + "\n\n" + "\n\n".join(parts)

    # =========================================================================
    # 消息组装（供引擎调用）
    # =========================================================================

    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        media: list[str] | None = None,
        attachments: list[Any] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        available_tools: set[str] | None = None,
        prompt_mode: str = "full",
        prepend_context: str | None = None,
        append_context: str | None = None,
    ) -> list[dict[str, Any]]:
        messages = []
        system_prompt = self.build_system_prompt(
            channel=channel,
            chat_id=chat_id,
            available_tools=available_tools,
            prompt_mode=prompt_mode,
            prepend_context=prepend_context,
            append_context=append_context,
        )
        messages.append({"role": "system", "content": system_prompt})
        messages.extend(history)
        user_content = self._build_user_content(current_message, media, attachments)
        messages.append({"role": "user", "content": user_content})
        return messages

    def _build_user_content(
        self,
        text: str,
        media: list[str] | None,
        attachments: list[Any] | None = None,
    ) -> str | list[dict[str, Any]]:
        """
        构建用户消息内容，支持：
        - media: 图片 URL 列表（直接 image_url block）
        - attachments: FileExtractResult 列表（包含文本/图片/描述）

        对标 openclaw content block 组装逻辑。
        """
        blocks: list[dict[str, Any]] = []

        # 1. media 图片（URL 或本地路径）
        for path in (media or []):
            if path.startswith("http://") or path.startswith("https://"):
                blocks.append({"type": "image_url", "image_url": {"url": path}})
                continue
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            if p.is_file() and mime and mime.startswith("image/"):
                b64 = base64.b64encode(p.read_bytes()).decode()
                blocks.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

        # 2. attachments（FileExtractResult 列表）
        extra_text_parts: list[str] = []
        for att in (attachments or []):
            # 纯图片附件（如图片文件）
            if att.images and not att.text:
                for img in att.images:
                    blocks.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{img.mime_type};base64,{img.data}"},
                    })
                continue

            # PDF 图片 fallback：既有少量文字又有图片（扫描件）
            if att.images:
                for img in att.images:
                    blocks.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{img.mime_type};base64,{img.data}"},
                    })

            # 文本内容：包裹在 <attachment> 标签内，LLM 可感知文件名
            if att.text:
                tag = f'<attachment name="{att.filename}">\n{att.text}\n</attachment>'
                extra_text_parts.append(tag)

            # 无法提取：仅描述
            if att.description and not att.text and not att.images:
                extra_text_parts.append(att.description)

        # 3. 组装最终 content
        full_text = text
        if extra_text_parts:
            suffix = "\n\n".join(extra_text_parts)
            full_text = f"{text}\n\n{suffix}" if text else suffix

        if not blocks:
            return full_text
        blocks.append({"type": "text", "text": full_text})
        return blocks

    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str,
    ) -> list[dict[str, Any]]:
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result,
        })
        return messages

    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
    ) -> list[dict[str, Any]]:
        msg: dict[str, Any] = {"role": "assistant", "content": content or ""}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        messages.append(msg)
        return messages
