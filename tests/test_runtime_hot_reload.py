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
        media_runtime=MagicMock(),
        engine=MagicMock(),
        workspace=MagicMock(),
        plugin_registry=MagicMock(),
        plugin_registry_factory=MagicMock(),
        merge_plugin_settings=MagicMock(),
        channel_runtime=MagicMock(),
        message_tool_sync=MagicMock(),
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
        media_runtime=MagicMock(),
        engine=MagicMock(),
        workspace=MagicMock(),
        plugin_registry=MagicMock(),
        plugin_registry_factory=MagicMock(),
        merge_plugin_settings=MagicMock(),
        channel_runtime=MagicMock(),
        message_tool_sync=MagicMock(),
    )

    result = await service.apply({"LLM_TEMPERATURE": 0.3}, ["LLM_TEMPERATURE"])

    assert result == {
        "applied": ["LLM_TEMPERATURE"],
        "requiresRestart": [],
        "issues": [],
    }
    agent.reload_runtime_config.assert_awaited_once_with({"LLM_TEMPERATURE": 0.3})


@pytest.mark.asyncio
async def test_hot_apply_refreshes_plugin_hooks() -> None:
    hooks = object()
    next_registry = MagicMock()
    next_registry.build_hook_runner.return_value = hooks
    plugin_registry_factory = MagicMock(return_value=next_registry)
    merge_plugin_settings = MagicMock(
        return_value=SimpleNamespace(
            enabled=True,
            allow=[],
            deny=[],
            load_paths=[],
            entries={},
        )
    )
    agent = MagicMock()
    agent.reload_runtime_config = AsyncMock(return_value={"applied": [], "requiresRestart": [], "issues": []})
    service = RuntimeHotApplyService(
        config=SimpleNamespace(
            RUNTIME_HOT_APPLY_ENABLED=True,
            PLUGINS_AUTO_DISCOVERY_ENABLED=True,
            PLUGINS_ENABLED=True,
            PLUGINS_ALLOW=[],
            PLUGINS_DENY=[],
            PLUGINS_LOAD_PATHS=[],
            PLUGINS_ENTRIES={},
        ),
        agent=agent,
        heartbeat=MagicMock(),
        stt_runtime=MagicMock(),
        media_runtime=MagicMock(),
        engine=MagicMock(),
        workspace="workspace",
        plugin_registry=MagicMock(),
        plugin_registry_factory=plugin_registry_factory,
        merge_plugin_settings=merge_plugin_settings,
        channel_runtime=MagicMock(),
        message_tool_sync=MagicMock(),
    )

    result = await service.apply({"PLUGINS_ENABLED": True}, ["PLUGINS_ENABLED"])

    assert result == {
        "applied": ["PLUGINS_ENABLED"],
        "requiresRestart": [],
        "issues": [],
    }
    assert service.plugin_registry is next_registry
    assert agent.hooks is hooks
    assert agent.assembler._hooks is hooks
    assert agent._runner._hooks is hooks

