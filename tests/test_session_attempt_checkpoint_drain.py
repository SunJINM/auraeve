from unittest.mock import AsyncMock, MagicMock

import pytest

import auraeve.config  # noqa: F401

from auraeve.agent_runtime.session_attempt import SessionAttemptRunner
from auraeve.providers.base import LLMResponse


@pytest.mark.asyncio
async def test_checkpoint_messages_are_injected_before_provider_call() -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=LLMResponse(content="done"))

    tools = MagicMock()
    tools.get_definitions.return_value = []

    hooks = MagicMock()
    hooks.run_before_model_resolve = AsyncMock(return_value=None)

    runner = SessionAttemptRunner(
        provider=provider,
        tools=tools,
        policy=MagicMock(),
        hooks=hooks,
        checkpoint_drain=lambda **_: [{"role": "user", "content": "checkpoint event"}],
    )

    result = await runner.run(
        messages=[{"role": "system", "content": "sys"}],
        model="test-model",
        temperature=0.0,
        max_tokens=256,
        thread_id="webui:s1",
    )

    assert result.final_content == "done"
    sent_messages = provider.chat.await_args.kwargs["messages"]
    assert sent_messages[-1] == {"role": "user", "content": "checkpoint event"}
