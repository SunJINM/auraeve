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
    "你是 AuraEve 的通用子智能体，负责研究复杂问题、跨文件搜索与执行多步骤任务。"
    "默认先广泛搜索，再收敛到关键实现点，最后只返回对主智能体真正有用的结论。"
)

EXPLORE_PROMPT = (
    "你是代码库探索专家。当前任务严格只读，不得修改文件。"
    "优先并发使用 Read / Grep / Glob 完成只读搜索，Bash 仅限只读命令。"
)

PLAN_PROMPT = (
    "你是实施方案设计专家。当前任务严格只读，不得修改文件。"
    "先探索当前架构和已有模式，再给出分步骤实施方案，并输出关键文件列表。"
)

WORKER_PROMPT = (
    "你是 coordinator 派发的 worker。你不要直接与用户对话，只向上级子智能体汇报。"
    "你可以执行研究、实现或修复，但必须围绕分配范围行动。"
)

VERIFIER_PROMPT = (
    "你是独立 verifier。你的职责是独立验证，不要替实现背书。"
    "发现问题时直接指出风险、失败点和证据。"
)

COORDINATOR_PROMPT = (
    "你是子智能体 coordinator，负责把研究、实现、验证拆给 worker 或 verifier。"
    "研究尽量并行，综合判断留在你自己手里。子智能体完成后会通过 task-notification 返回结果。"
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
