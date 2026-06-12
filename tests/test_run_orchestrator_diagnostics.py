from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auraeve.agent_runtime.run_orchestrator import RunOrchestrator
from auraeve.providers.base import LLMCallError


@pytest.mark.asyncio
async def test_orchestrator_logs_llm_call_error_before_retry() -> None:
    runner = MagicMock()
    runner.run = AsyncMock(side_effect=LLMCallError("connection failed"))
    orchestrator = RunOrchestrator(runner=runner, provider=MagicMock(), max_retries=2)
    orchestrator._obs = MagicMock()

    with patch("auraeve.agent_runtime.run_orchestrator.asyncio.sleep", AsyncMock()), patch(
        "auraeve.agent_runtime.run_orchestrator.logger.warning"
    ) as warning_mock:
        result = await orchestrator.run(
            messages=[{"role": "user", "content": "hi"}],
            model="model",
            temperature=0,
            max_tokens=10,
            thread_id="webui:test",
        )

    assert result.error_class == "LLMCallError"
    warning_mock.assert_called_once()
    assert "connection failed" in warning_mock.call_args.args[0]
