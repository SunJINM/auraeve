"""Agent 定义系统测试。"""
from auraeve.agent.agents.definitions import (
    AgentDefinition,
    GENERAL_PURPOSE_AGENT,
    EXPLORE_AGENT,
    PLAN_AGENT,
    get_builtin_agents,
    find_agent,
)


def test_general_purpose_agent():
    a = GENERAL_PURPOSE_AGENT
    assert a.agent_type == "general-purpose"
    assert "*" in a.tools
    assert a.is_builtin is True


def test_explore_agent():
    a = EXPLORE_AGENT
    assert a.agent_type == "explore"
    assert "Write" not in a.tools
    assert "agent" in a.disallowed_tools
    assert a.permission_mode == "bypass"


def test_plan_agent():
    a = PLAN_AGENT
    assert a.agent_type == "plan"
    assert "agent" in a.disallowed_tools
    assert a.permission_mode == "bypass"


def test_explore_agent_uses_read_replacement_names():
    a = EXPLORE_AGENT
    assert "Read" in a.tools
    assert "Write" not in a.tools
    assert "Edit" not in a.tools
    assert "agent" in a.disallowed_tools
    assert "Edit" in a.disallowed_tools


def test_get_builtin_agents():
    agents = get_builtin_agents()
    types = [a.agent_type for a in agents]
    assert "general-purpose" in types
    assert "explore" in types
    assert "plan" in types


def test_find_agent_builtin():
    a = find_agent("explore")
    assert a is not None
    assert a.agent_type == "explore"


def test_find_agent_default():
    a = find_agent("nonexistent")
    assert a is not None
    assert a.agent_type == "general-purpose"


def test_custom_agent_definition():
    a = AgentDefinition(
        agent_type="my-agent",
        when_to_use="自定义用途",
        tools=["Read", "exec"],
        disallowed_tools=["agent", "Edit"],
        max_turns=20,
    )
    assert a.agent_type == "my-agent"
    assert a.max_turns == 20
    assert a.is_builtin is False
