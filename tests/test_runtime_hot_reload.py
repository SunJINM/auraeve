from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from auraeve.runtime_hot_reload import RuntimeHotApplyService


@pytest.mark.asyncio
async def test_hot_apply_returns_restart_only_when_disabled() -> None:
    service = RuntimeHotApplyService(
        config=SimpleNamespace(RUNTIME_HOT_APPLY_ENABLED=False),
        agent=MagicMock(),
        heartbeat=MagicMock(),
        stt_runtime=MagicMock(),
        engine=MagicMock(),
        workspace=MagicMock(),
        channel_runtime=MagicMock(),
    )

    result = await service.apply({"LLM_TEMPERATURE": 0.3}, ["LLM_TEMPERATURE"])

    assert result == {
        "applied": [],
        "requiresRestart": ["LLM_TEMPERATURE"],
        "issues": [],
    }


@pytest.mark.asyncio
async def test_hot_apply_delegates_core_runtime_patch() -> None:
    agent = MagicMock()
    agent.reload_runtime_config = AsyncMock(
        return_value={"applied": ["LLM_TEMPERATURE"], "requiresRestart": [], "issues": []}
    )
    service = RuntimeHotApplyService(
        config=SimpleNamespace(RUNTIME_HOT_APPLY_ENABLED=True),
        agent=agent,
        heartbeat=MagicMock(),
        stt_runtime=MagicMock(),
        engine=MagicMock(),
        workspace=MagicMock(),
        channel_runtime=MagicMock(),
    )

    result = await service.apply({"LLM_TEMPERATURE": 0.3}, ["LLM_TEMPERATURE"])

    assert result == {
        "applied": ["LLM_TEMPERATURE"],
        "requiresRestart": [],
        "issues": [],
    }
    agent.reload_runtime_config.assert_awaited_once_with({"LLM_TEMPERATURE": 0.3})


