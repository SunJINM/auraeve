from unittest.mock import AsyncMock, MagicMock

import pytest

from auraeve.agent_runtime.session_attempt import SessionAttemptRunner
from auraeve.providers.base import LLMResponse, ToolCallRequest


@pytest.mark.asyncio
async def test_subagent_budget_exhaustion_uses_llmresponse_content_for_summary() -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(
        side_effect=[
            LLMResponse(
                content="need tool",
                tool_calls=[ToolCallRequest(id="tool-1", name="search", arguments={"q": "x"})],
            ),
            LLMResponse(content="基于已收集信息的汇总"),
        ]
    )

    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.get_metadata.return_value = {}
    tools.execute = AsyncMock(return_value="ok")

    policy = MagicMock()
    policy.infer_tool_group.return_value = "search"
    policy.evaluate = AsyncMock(return_value=MagicMock(allowed=True, rewritten_args={"q": "x"}, reason=""))

    runner = SessionAttemptRunner(
        provider=provider,
        tools=tools,
        policy=policy,
        max_iterations=1,
        runtime_execution={"maxTurns": 1, "maxToolCallsTotal": 10, "maxToolCallsPerTurn": 10},
    )

    result = await runner.run(
        messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "go"}],
        model="test-model",
        temperature=0.0,
        max_tokens=256,
        thread_id="sub:task-1",
        is_subagent=True,
    )

    assert result.final_content == "基于已收集信息的汇总"
