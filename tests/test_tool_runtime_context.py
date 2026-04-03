from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import auraeve.config  # noqa: F401

from auraeve.agent_runtime.session_attempt import SessionAttemptRunner
from auraeve.agent_runtime.tool_runtime_context import get_current_tool_runtime_context
from auraeve.providers.base import LLMResponse, ToolCallRequest


class _ContextProbeTool:
    name = "ContextProbe"
    description = "probe"
    parameters = {"type": "object", "properties": {}, "required": []}

    def validate_params(self, _params):
        return []

    async def execute(self, **_kwargs):
        ctx = get_current_tool_runtime_context()
        assert ctx is not None
        assert ctx.file_reads is not None
        return f"tracked={len(ctx.file_reads.snapshots)}"


@pytest.mark.asyncio
async def test_runner_exposes_file_read_state_inside_tool_execution() -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(
        side_effect=[
            LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(id="call_1", name="ContextProbe", arguments={})],
            ),
            LLMResponse(content="done"),
        ]
    )
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.get_metadata.return_value = {}
    probe = _ContextProbeTool()

    async def _execute(_name, _params):
        return await probe.execute()

    tools.execute = AsyncMock(side_effect=_execute)
    hooks = MagicMock()
    hooks.run_before_model_resolve = AsyncMock(return_value=None)
    hooks.run_before_tool_call = AsyncMock(return_value=MagicMock(block=False, params=None))
    hooks.run_after_tool_call = AsyncMock()
    policy = MagicMock()
    policy.infer_tool_group.return_value = "filesystem"
    policy.evaluate = AsyncMock(
        return_value=MagicMock(allowed=True, rewritten_args={}, reason="")
    )

    runner = SessionAttemptRunner(
        provider=provider,
        tools=tools,
        policy=policy,
        hooks=hooks,
        max_iterations=2,
    )
    result = await runner.run(
        messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "go"}],
        model="test-model",
        temperature=0.0,
        max_tokens=128,
        thread_id="webui:test",
    )

    assert result.final_content == "done"
    assert "tracked=0" in result.messages[1]["content"]
