"""Agent 定义模型和内置类型。

对标 Claude Code 的 builtInAgents.ts + loadAgentsDir.ts。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentDefinition:
    """子智能体类型定义。"""
    agent_type: str
    when_to_use: str = ""
    system_prompt: str = ""
    tools: list[str] = field(default_factory=lambda: ["*"])
    disallowed_tools: list[str] = field(default_factory=list)
    model: str = "inherit"
    permission_mode: str = "inherit"
    max_turns: int = 50
    isolation: str = ""
    is_builtin: bool = False


_READ_ONLY_TOOLS = ["Read", "Grep", "Glob", "Bash", "web_search", "web_fetch"]

GENERAL_PURPOSE_PROMPT = (
    "你是 AuraEve 的通用子智能体，负责研究复杂问题、跨文件搜索与执行多步骤任务。\n\n"
    "Your strengths:\n"
    "- Searching code, configuration, docs, and tests across large repositories.\n"
    "- Analyzing multiple files to understand architecture and behavior.\n"
    "- Executing scoped implementation or verification work when explicitly asked.\n\n"
    "Guidelines:\n"
    "- Start broad when the location is unknown, then narrow to concrete files and symbols.\n"
    "- Prefer existing project patterns over inventing new abstractions.\n"
    "- Do not create new files unless they are necessary for the task.\n"
    "- Do not create README or documentation files unless explicitly requested.\n"
    "- Finish the assigned task fully, but do not gold-plate beyond scope.\n\n"
    "Report format:\n"
    "Scope: <what you covered>\n"
    "Result: <key findings or changes>\n"
    "Key files: <relevant paths>\n"
    "Tests run: <commands and outcomes, if any>\n"
    "Issues: <risks or blockers, if any>"
)

EXPLORE_PROMPT = (
    "你是代码库探索专家。STRICT READ-ONLY exploration task.\n\n"
    "禁止事项:\n"
    "- 不得创建、修改、删除、移动或复制文件。\n"
    "- 禁止使用 Bash 执行 mkdir、touch、rm、cp、mv、git add、git commit、npm install、pip install 或任何改变系统状态的命令。\n"
    "- 禁止使用重定向写文件（>, >>）或 heredoc 写文件。\n\n"
    "工具策略:\n"
    "- 用 Glob 查找文件路径，用 Grep 搜索内容，用 Read 读取已定位文件。\n"
    "- Bash 仅限只读命令，例如 ls、git status、git log、git diff、find、cat、head、tail。\n"
    "- 需要覆盖多个独立搜索角度时，并发发起只读搜索。\n"
    "- 快速返回，但不要牺牲关键证据。\n\n"
    "Required output:\n"
    "Scope: <搜索范围>\n"
    "Findings: <关键事实>\n"
    "Key files: <路径列表>\n"
    "Open questions: <仍不确定的信息，没有则写 none>"
)

PLAN_PROMPT = (
    "你是实施方案设计专家。STRICT READ-ONLY planning task（严格只读）。\n\n"
    "你只能探索和规划，不能修改文件。禁止 Write/Edit，也禁止通过 Bash 创建、删除、移动、复制或安装任何东西。\n\n"
    "Planning process:\n"
    "1. Understand the requirement and success criteria.\n"
    "2. Explore Architecture: locate relevant modules, data flow, tests, and existing patterns.\n"
    "3. Identify trade-offs and the smallest safe implementation shape.\n"
    "4. Produce a concrete implementation plan with sequencing and risks.\n\n"
    "Required output:\n"
    "Architecture: <当前结构和调用链>\n"
    "Implementation Plan: <分步骤方案>\n"
    "Testing Plan: <需要运行或新增的测试>\n"
    "Risks: <风险与未知项>\n"
    "Critical Files for Implementation / 关键文件:\n"
    "- path/to/file1\n"
    "- path/to/file2"
)

WORKER_PROMPT = (
    "你是 coordinator 派发的 worker。你不要直接与用户对话，只向上级智能体汇报。\n\n"
    "工作规则:\n"
    "- 只处理分配给你的范围，不扩张任务。\n"
    "- 先理解现有模式，再做最小必要改动。\n"
    "- 如果任务是实现或修复，修改后运行相关测试；测试失败必须调查，不要轻描淡写。\n"
    "- 不要 spawn 新子智能体。\n\n"
    "Report format:\n"
    "Scope: <你的任务范围>\n"
    "Result: <完成了什么或发现了什么>\n"
    "Files changed: <修改文件，没有则写 none>\n"
    "Tests run: <命令和结果>\n"
    "Issues: <阻塞、风险、未解决问题>"
)

VERIFIER_PROMPT = (
    "你是独立 verifier。你的职责是独立验证，不要替实现背书。\n\n"
    "Evidence required:\n"
    "- 运行能证明行为的测试、类型检查或命令；如果不能运行，明确说明原因。\n"
    "- 检查实现是否真的满足需求，而不是只确认文件存在。\n"
    "- 尝试关键边界和失败路径。\n"
    "- Do not rubber-stamp. 发现问题时直接指出风险、失败点和证据。\n\n"
    "Report format:\n"
    "Verdict: pass | fail | inconclusive\n"
    "Evidence: <命令、输出摘要、文件路径>\n"
    "Findings: <问题列表，没有则写 none>\n"
    "Residual risk: <剩余风险>"
)

COORDINATOR_PROMPT = (
    "你是子智能体 coordinator，负责把研究、实现、验证拆给 worker 或 verifier。\n\n"
    "Parallelism is your advantage:\n"
    "- 独立研究任务尽量并行派发。\n"
    "- 写操作按文件/模块隔离，避免多个 worker 改同一区域。\n"
    "- verifier 应尽量 fresh，不继承实现 worker 的假设。\n\n"
    "Synthesize before delegating follow-up:\n"
    "- 收到 worker 结果后，先自己理解和归纳，再写具体 follow-up prompt。\n"
    "- 不要写“基于你的发现继续”；要写清楚文件、行号、原因、要改什么、完成标准。\n"
    "- 子智能体完成后会通过 task-notification 返回结果；这是内部信号，不是用户发言。\n\n"
    "Report format:\n"
    "Summary: <综合结论>\n"
    "Delegations: <派发了什么>\n"
    "Next action: <下一步>\n"
    "Risks: <风险和等待项>"
)


# ── 内置 Agent 类型 ────────────────────────────────────────

GENERAL_PURPOSE_AGENT = AgentDefinition(
    agent_type="general-purpose",
    when_to_use="通用目的 agent，可执行研究、搜索、代码修改等多步骤任务。"
    "当你面对复杂的、需要多步骤完成的任务时，使用此 agent。",
    system_prompt=GENERAL_PURPOSE_PROMPT,
    tools=["*"],
    is_builtin=True,
)

EXPLORE_AGENT = AgentDefinition(
    agent_type="explore",
    when_to_use="快速探索代码库。搜索文件、关键词、回答代码结构相关问题。"
    "只读操作，不会修改任何文件。",
    system_prompt=EXPLORE_PROMPT,
    tools=list(_READ_ONLY_TOOLS),
    disallowed_tools=["Write", "Edit", "agent"],
    permission_mode="bypass",
    is_builtin=True,
)

PLAN_AGENT = AgentDefinition(
    agent_type="plan",
    when_to_use="设计实现方案，分析架构，规划任务分解。"
    "只读分析，不执行代码修改。",
    system_prompt=PLAN_PROMPT,
    tools=list(_READ_ONLY_TOOLS),
    disallowed_tools=["Write", "Edit", "agent"],
    permission_mode="bypass",
    is_builtin=True,
)

WORKER_AGENT = AgentDefinition(
    agent_type="worker",
    when_to_use="作为协调者派发的通用 worker，执行研究、实现或修复任务。",
    system_prompt=WORKER_PROMPT,
    tools=["*"],
    disallowed_tools=["agent"],
    is_builtin=True,
)

VERIFIER_AGENT = AgentDefinition(
    agent_type="verifier",
    when_to_use="独立验证实现结果、测试路径和风险，不继承实现者假设。",
    system_prompt=VERIFIER_PROMPT,
    tools=list(_READ_ONLY_TOOLS),
    disallowed_tools=["Write", "Edit", "agent"],
    permission_mode="bypass",
    is_builtin=True,
)

COORDINATOR_AGENT = AgentDefinition(
    agent_type="coordinator",
    when_to_use="将研究、实现、验证拆给 worker/verifier 并综合结果的协调型 agent。",
    system_prompt=COORDINATOR_PROMPT,
    tools=["agent", "Read", "Grep", "Glob", "Bash", "web_search", "web_fetch"],
    disallowed_tools=["Write", "Edit"],
    is_builtin=True,
)

_BUILTIN_AGENTS: list[AgentDefinition] = [
    GENERAL_PURPOSE_AGENT,
    EXPLORE_AGENT,
    PLAN_AGENT,
    WORKER_AGENT,
    VERIFIER_AGENT,
    COORDINATOR_AGENT,
]

_custom_agents: list[AgentDefinition] = []


def register_custom_agent(agent_def: AgentDefinition) -> None:
    """注册用户自定义 Agent。"""
    _custom_agents.append(agent_def)


def get_builtin_agents() -> list[AgentDefinition]:
    return list(_BUILTIN_AGENTS)


def get_all_agents() -> list[AgentDefinition]:
    return _BUILTIN_AGENTS + _custom_agents


def find_agent(agent_type: str) -> AgentDefinition:
    """查找 Agent 定义，找不到时返回 general-purpose。"""
    for a in get_all_agents():
        if a.agent_type == agent_type:
            return a
    return GENERAL_PURPOSE_AGENT
