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
