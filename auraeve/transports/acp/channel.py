"""ACPChannel：ACP WebSocket 渠道，继承 BaseChannel。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger

from auraeve.bus.events import OutboundMessage
from auraeve.channels.base import BaseChannel
from auraeve.transports.acp.connection import ACPConnectionHandler
from auraeve.transports.acp.dispatcher import ACPDispatcher
from auraeve.transports.acp.event_mapper import EventMapper

if TYPE_CHECKING:
    from auraeve.bus.queue import MessageBus
    from auraeve.services.session_service import SessionService


@dataclass
class ACPChannelConfig:
    allow_from: list[str] = field(default_factory=list)


class ACPChannel(BaseChannel):
    """
    ACP WebSocket 渠道。

    入站：Claude Code 通过 WebSocket 发 JSON-RPC → dispatcher → bus.publish_inbound()
    出站：bus 将 OutboundMessage 路由到对应 ACPConnectionHandler → 客户端
    """

    name = "acp"

    def __init__(
        self,
        config: ACPChannelConfig,
        bus: "MessageBus",
        session_service: "SessionService",
        token: str = "",
        agent_id: str = "main",
        workspace_id: str = "default",
    ) -> None:
        super().__init__(config, bus)
        self._token = token
        self._agent_id = agent_id
        self._workspace_id = workspace_id
        self._session_service = session_service
        self._dispatcher = ACPDispatcher(
            bus=bus,
            session_service=session_service,
            agent_id=agent_id,
            workspace_id=workspace_id,
        )
        self._mapper = EventMapper()
        self._active_handlers: list[ACPConnectionHandler] = []

    async def start(self) -> None:
        self._running = True
        # 路由由 WebUIServer 注册，此处仅标记启动状态
        while self._running:
            await asyncio.sleep(3600)

    async def stop(self) -> None:
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        """出站消息：由 bus 直接路由到对应 handler，此方法不使用。"""

    def build_websocket_handler(self):
        """返回一个可注册到 FastAPI 的 WebSocket handler 协程。"""
        channel = self

        async def websocket_endpoint(websocket: Any) -> None:
            token = websocket.query_params.get("token", "")
            if channel._token and token != channel._token:
                await websocket.close(code=4401)
                return

            await websocket.accept()
            handler = ACPConnectionHandler(
                dispatcher=channel._dispatcher,
                bus=channel.bus,
                event_mapper=channel._mapper,
            )
            channel._active_handlers.append(handler)
            try:
                await handler.run(websocket)
            finally:
                channel._active_handlers.remove(handler)

        return websocket_endpoint
