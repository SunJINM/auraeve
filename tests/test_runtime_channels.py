import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from auraeve.runtime_channels import ChannelRuntimeManager


class _FakeChannel:
    def __init__(self, name: str) -> None:
        self.name = name
        self.config = SimpleNamespace(allow_from=[], allow_groups=[])
        self.send = MagicMock()
        self._call_action = MagicMock()
        self._friend_flags = {}
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class _FakeMessageTool:
    def __init__(self) -> None:
        self._direct_senders = {"napcat": object()}


class _FakeTools:
    def __init__(self) -> None:
        self.tool_names = ["napcat_send", "other"]
        self.unregistered: list[str] = []

    def unregister(self, name: str) -> None:
        self.unregistered.append(name)
        self.tool_names = [item for item in self.tool_names if item != name]

    def get(self, name: str):
        if name == "message":
            return _FakeMessageTool()
        return None


@pytest.mark.asyncio
async def test_manager_no_fallback_terminal_when_no_channels_configured() -> None:
    """所有渠道关闭时不应自动启动终端模式。"""
    terminal_channel = _FakeChannel("terminal")
    bus = MagicMock()
    manager = ChannelRuntimeManager(
        config=SimpleNamespace(
            DINGTALK_ENABLED=False,
            DINGTALK_CLIENT_ID="",
            DINGTALK_CLIENT_SECRET="",
            NAPCAT_ENABLED=False,
        ),
        bus=bus,
        agent=MagicMock(command_queue=object(), tools=_FakeTools()),
        workspace=Path("."),
        terminal_factory=lambda queue: terminal_channel,
        dingtalk_factory=MagicMock(),
        napcat_factory=MagicMock(),
        napcat_tool_factory=MagicMock(return_value=[]),
    )

    await manager.start_initial_channels(terminal_mode=False)

    assert manager.channels == []
    bus.subscribe_outbound.assert_not_called()


@pytest.mark.asyncio
async def test_manager_starts_terminal_when_explicitly_requested() -> None:
    """显式指定 terminal_mode=True 时应启动终端。"""
    terminal_channel = _FakeChannel("terminal")
    bus = MagicMock()
    manager = ChannelRuntimeManager(
        config=SimpleNamespace(
            DINGTALK_ENABLED=False,
            DINGTALK_CLIENT_ID="",
            DINGTALK_CLIENT_SECRET="",
            NAPCAT_ENABLED=False,
        ),
        bus=bus,
        agent=MagicMock(command_queue=object(), tools=_FakeTools()),
        workspace=Path("."),
        terminal_factory=lambda queue: terminal_channel,
        dingtalk_factory=MagicMock(),
        napcat_factory=MagicMock(),
        napcat_tool_factory=MagicMock(return_value=[]),
    )

    await manager.start_initial_channels(terminal_mode=True)

    assert manager.channels == [terminal_channel]
    bus.subscribe_outbound.assert_called_once_with("terminal", terminal_channel.send)


@pytest.mark.asyncio
async def test_manager_starts_and_stops_dingtalk() -> None:
    dingtalk_channel = _FakeChannel("dingtalk")
    bus = MagicMock()
    manager = ChannelRuntimeManager(
        config=SimpleNamespace(
            DINGTALK_ENABLED=True,
            DINGTALK_CLIENT_ID="app-key",
            DINGTALK_CLIENT_SECRET="app-secret",
            DINGTALK_ALLOW_FROM=[],
            NAPCAT_ENABLED=False,
        ),
        bus=bus,
        agent=MagicMock(command_queue=object(), tools=_FakeTools()),
        workspace=Path("."),
        terminal_factory=MagicMock(),
        dingtalk_factory=lambda config, queue, workspace: dingtalk_channel,
        napcat_factory=MagicMock(),
        napcat_tool_factory=MagicMock(return_value=[]),
    )

    started = await manager.start_dingtalk()
    await asyncio.sleep(0)
    await manager.stop_dingtalk()

    assert started is True
    assert dingtalk_channel.started is True
    assert dingtalk_channel.stopped is True
    assert manager.get_dingtalk_channel() is None
    bus.subscribe_outbound.assert_called_once_with("dingtalk", dingtalk_channel.send)
    bus.unsubscribe_outbound.assert_called_once_with("dingtalk", dingtalk_channel.send)


@pytest.mark.asyncio
async def test_manager_starts_and_stops_napcat_and_cleans_tools() -> None:
    napcat_channel = _FakeChannel("napcat")
    bus = MagicMock()
    agent = MagicMock(command_queue=object(), tools=_FakeTools())
    agent.register_channel_sender = MagicMock()
    agent.register_tool = MagicMock()
    manager = ChannelRuntimeManager(
        config=SimpleNamespace(
            DINGTALK_ENABLED=False,
            DINGTALK_CLIENT_ID="",
            DINGTALK_CLIENT_SECRET="",
            NAPCAT_ENABLED=True,
            NAPCAT_WS_URL="ws://127.0.0.1:3001",
            NAPCAT_ACCESS_TOKEN="",
            NAPCAT_ALLOW_FROM=[],
            NAPCAT_ALLOW_GROUPS=[],
        ),
        bus=bus,
        agent=agent,
        workspace=Path("."),
        terminal_factory=MagicMock(),
        dingtalk_factory=MagicMock(),
        napcat_factory=lambda config, queue: napcat_channel,
        napcat_tool_factory=MagicMock(return_value=["tool-a", "tool-b"]),
    )

    started = await manager.start_napcat()
    await asyncio.sleep(0)
    await manager.stop_napcat()

    assert started is True
    assert napcat_channel.started is True
    assert napcat_channel.stopped is True
    assert "napcat_send" in agent.tools.unregistered
    agent.register_channel_sender.assert_called_once_with("napcat", napcat_channel.send)
    assert agent.register_tool.call_count == 2
    bus.subscribe_outbound.assert_called_once_with("napcat", napcat_channel.send)
    bus.unsubscribe_outbound.assert_called_once_with("napcat", napcat_channel.send)


def test_main_no_longer_contains_embedded_channel_lifecycle_helpers() -> None:
    result = subprocess.run(
        ["rg", "-n", "async def _start_dingtalk_channel|async def _start_napcat_channel|channels = \\[\\]", "main.py"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
