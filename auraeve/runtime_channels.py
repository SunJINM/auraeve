from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from auraeve.bus.queue import OutboundDispatcher
from auraeve.channels.dingtalk import DingTalkChannel, DingTalkConfig
from auraeve.channels.napcat import NapCatChannel, NapCatConfig
from auraeve.channels.terminal import TerminalChannel, TerminalConfig
from auraeve.runtime_hot_reload import ChannelRuntimeControls


class ChannelRuntimeManager:
    def __init__(
        self,
        *,
        config,
        bus: OutboundDispatcher,
        agent,
        workspace: Path,
        terminal_factory: Callable[[Any], Any] | None = None,
        dingtalk_factory: Callable[[Any, Any, Path], Any] | None = None,
        napcat_factory: Callable[[Any, Any], Any] | None = None,
        napcat_tool_factory: Callable[[Any, Any, Path], list[Any]] | None = None,
    ) -> None:
        self.config = config
        self.bus = bus
        self.agent = agent
        self.workspace = workspace
        self._terminal_factory = terminal_factory or (
            lambda queue: TerminalChannel(TerminalConfig(), queue)
        )
        self._dingtalk_factory = dingtalk_factory or (
            lambda channel_config, queue, workspace: DingTalkChannel(
                channel_config,
                queue,
                workspace=workspace,
            )
        )
        self._napcat_factory = napcat_factory or (
            lambda channel_config, queue: NapCatChannel(channel_config, queue)
        )
        self._napcat_tool_factory = napcat_tool_factory
        self.channels: list[Any] = []
        self.channel_tasks: dict[str, asyncio.Task] = {}
        self._dingtalk_channel = None
        self._napcat_channel = None

    def is_dingtalk_configured(self) -> bool:
        return bool(
            getattr(self.config, "DINGTALK_ENABLED", True)
            and getattr(self.config, "DINGTALK_CLIENT_ID", "")
            and getattr(self.config, "DINGTALK_CLIENT_SECRET", "")
            and self.config.DINGTALK_CLIENT_ID not in ("", "your-app-key")
            and self.config.DINGTALK_CLIENT_SECRET not in ("", "your-app-secret")
        )

    def is_napcat_enabled(self) -> bool:
        return bool(getattr(self.config, "NAPCAT_ENABLED", False))

    def get_dingtalk_channel(self):
        return self._dingtalk_channel

    def get_napcat_channel(self):
        return self._napcat_channel

    async def start_initial_channels(self, *, terminal_mode: bool) -> None:
        if terminal_mode:
            self.add_terminal_channel()
        if self.is_dingtalk_configured():
            await self.start_dingtalk()
        if self.is_napcat_enabled():
            await self.start_napcat()
        if not self.channels:
            logger.warning("没有任何渠道启动，使用 --terminal 启动终端模式")

    def add_terminal_channel(self) -> Any:
        terminal_channel = self._terminal_factory(self.agent.command_queue)
        self.bus.subscribe_outbound("terminal", terminal_channel.send)
        self.channels.append(terminal_channel)
        return terminal_channel

    async def start_dingtalk(self) -> bool:
        if self._dingtalk_channel is not None:
            return True
        if not self.is_dingtalk_configured():
            return False
        channel_config = DingTalkConfig(
            client_id=self.config.DINGTALK_CLIENT_ID,
            client_secret=self.config.DINGTALK_CLIENT_SECRET,
            allow_from=self.config.DINGTALK_ALLOW_FROM,
        )
        channel = self._dingtalk_factory(channel_config, self.agent.command_queue, self.workspace)
        self._dingtalk_channel = channel
        self.bus.subscribe_outbound("dingtalk", channel.send)
        self.channels.append(channel)
        self.channel_tasks["dingtalk"] = asyncio.create_task(channel.start())
        logger.info("Channel: DingTalk started")
        return True

    async def stop_dingtalk(self) -> None:
        if self._dingtalk_channel is None:
            return
        channel = self._dingtalk_channel
        self._dingtalk_channel = None
        self._remove_channel_task("dingtalk")
        self.bus.unsubscribe_outbound("dingtalk", channel.send)
        await channel.stop()
        self._remove_channel(channel)
        logger.info("Channel: DingTalk stopped")

    async def restart_dingtalk(self) -> bool:
        await self.stop_dingtalk()
        return await self.start_dingtalk()

    async def start_napcat(self) -> bool:
        if self._napcat_channel is not None:
            return True
        if not self.is_napcat_enabled():
            return False
        channel_config = NapCatConfig(
            ws_url=getattr(self.config, "NAPCAT_WS_URL", "ws://127.0.0.1:3001"),
            access_token=getattr(self.config, "NAPCAT_ACCESS_TOKEN", ""),
            allow_from=getattr(self.config, "NAPCAT_ALLOW_FROM", []),
            allow_groups=getattr(self.config, "NAPCAT_ALLOW_GROUPS", []),
        )
        channel = self._napcat_factory(channel_config, self.agent.command_queue)
        self._napcat_channel = channel
        self.bus.subscribe_outbound("napcat", channel.send)
        self.agent.register_channel_sender("napcat", channel.send)
        self.channels.append(channel)
        self.channel_tasks["napcat"] = asyncio.create_task(channel.start())
        self._register_napcat_tools(channel)
        logger.info(f"Channel: NapCat/QQ ({channel_config.ws_url})")
        return True

    async def stop_napcat(self) -> None:
        if self._napcat_channel is None:
            self._remove_napcat_tools()
            return
        channel = self._napcat_channel
        self._napcat_channel = None
        self._remove_channel_task("napcat")
        self.bus.unsubscribe_outbound("napcat", channel.send)
        message_tool = self.agent.tools.get("message")
        if hasattr(message_tool, "_direct_senders"):
            message_tool._direct_senders.pop("napcat", None)
        self._remove_napcat_tools()
        await channel.stop()
        self._remove_channel(channel)
        logger.info("Channel: NapCat stopped")

    async def restart_napcat(self) -> bool:
        await self.stop_napcat()
        return await self.start_napcat()

    def start_unmanaged_channel_tasks(self) -> None:
        for channel in self.channels:
            if channel.name in self.channel_tasks:
                continue
            self.channel_tasks[channel.name] = asyncio.create_task(channel.start())

    async def stop_all(self) -> None:
        for task in list(self.channel_tasks.values()):
            if not task.done():
                task.cancel()
        self.channel_tasks.clear()
        for channel in list(self.channels):
            await channel.stop()
        self.channels.clear()
        self._dingtalk_channel = None
        self._napcat_channel = None

    def build_hot_reload_controls(self) -> ChannelRuntimeControls:
        return ChannelRuntimeControls(
            is_dingtalk_configured=self.is_dingtalk_configured,
            restart_dingtalk_channel=self.restart_dingtalk,
            stop_dingtalk_channel=self.stop_dingtalk,
            get_dingtalk_channel=self.get_dingtalk_channel,
            is_napcat_enabled=self.is_napcat_enabled,
            restart_napcat_channel=self.restart_napcat,
            stop_napcat_channel=self.stop_napcat,
            get_napcat_channel=self.get_napcat_channel,
        )

    def _remove_channel_task(self, name: str) -> None:
        task = self.channel_tasks.pop(name, None)
        if task and not task.done():
            task.cancel()

    def _remove_channel(self, target) -> None:
        self.channels = [channel for channel in self.channels if channel is not target]

    def _remove_napcat_tools(self) -> None:
        for name in list(self.agent.tools.tool_names):
            if name.startswith("napcat_"):
                self.agent.tools.unregister(name)

    def _register_napcat_tools(self, channel) -> None:
        self._remove_napcat_tools()
        tool_factory = self._napcat_tool_factory
        if tool_factory is None:
            from auraeve.agent.tools.napcat import create_napcat_tools

            tool_factory = create_napcat_tools
        media_dir = self.workspace / "media"
        for tool in tool_factory(channel._call_action, friend_flags=channel._friend_flags, media_dir=media_dir):
            self.agent.register_tool(tool)
