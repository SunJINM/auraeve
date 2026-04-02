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


# ── 内置 Agent 类型 ────────────────────────────────────────

GENERAL_PURPOSE_AGENT = AgentDefinition(
    agent_type="general-purpose",
    when_to_use="通用目的 agent，可执行研究、搜索、代码修改等多步骤任务。"
    "当你面对复杂的、需要多步骤完成的任务时，使用此 agent。",
    tools=["*"],
    is_builtin=True,
)

EXPLORE_AGENT = AgentDefinition(
    agent_type="explore",
    when_to_use="快速探索代码库。搜索文件、关键词、回答代码结构相关问题。"
    "只读操作，不会修改任何文件。",
    tools=["read_file", "list_dir", "exec", "web_search", "web_fetch"],
    disallowed_tools=["write_file", "edit_file", "agent"],
    permission_mode="bypass",
    is_builtin=True,
)

PLAN_AGENT = AgentDefinition(
    agent_type="plan",
    when_to_use="设计实现方案，分析架构，规划任务分解。"
    "只读分析，不执行代码修改。",
    tools=["read_file", "list_dir", "exec", "web_search", "web_fetch"],
    disallowed_tools=["write_file", "edit_file", "agent"],
    permission_mode="bypass",
    is_builtin=True,
)

_BUILTIN_AGENTS: list[AgentDefinition] = [
    GENERAL_PURPOSE_AGENT,
    EXPLORE_AGENT,
    PLAN_AGENT,
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
