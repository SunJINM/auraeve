import pytest

from auraeve.agent_runtime.tool_policy.contracts import PolicyContext
from auraeve.agent_runtime.tool_policy.engine import ToolPolicyEngine


@pytest.mark.asyncio
async def test_subagent_policy_denies_agent_tool():
    engine = ToolPolicyEngine()

    result = await engine.evaluate(
        PolicyContext(
            tool_name="agent",
            args={},
            session_id="session-1",
            is_subagent=True,
        )
    )

    assert result.allowed is False
    assert "agent" in result.reason
    assert any(item.rule_id == "subagent_deny_agent" for item in result.trace)


def test_infer_tool_group_treats_agent_as_agent_group():
    assert ToolPolicyEngine.infer_tool_group("agent") == "agent"


def test_infer_tool_group_treats_read_and_write_as_filesystem_group():
    assert ToolPolicyEngine.infer_tool_group("Read") == "filesystem"
    assert ToolPolicyEngine.infer_tool_group("Write") == "filesystem"
    assert ToolPolicyEngine.infer_tool_group("Edit") == "filesystem"


@pytest.mark.asyncio
async def test_write_is_tagged_as_high_risk_tool():
    engine = ToolPolicyEngine()

    result = await engine.evaluate(
        PolicyContext(
            tool_name="Write",
            args={},
            session_id="session-1",
            is_subagent=False,
        )
    )

    assert result.allowed is True
    assert any(item.rule_id == "risk_tag:high" for item in result.trace)


@pytest.mark.asyncio
async def test_edit_is_tagged_as_high_risk_tool():
    engine = ToolPolicyEngine()

    result = await engine.evaluate(
        PolicyContext(
            tool_name="Edit",
            args={},
            session_id="session-1",
            is_subagent=False,
        )
    )

    assert result.allowed is True
    assert any(item.rule_id == "risk_tag:high" for item in result.trace)
