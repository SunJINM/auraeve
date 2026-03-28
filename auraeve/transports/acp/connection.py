"""单 WebSocket 连接的生命周期管理。"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from loguru import logger

from auraeve.bus.events import OutboundMessage
from auraeve.transports.acp.event_mapper import EventMapper
from auraeve.transports.acp.protocol import (
    JsonRpcResponse, JsonRpcError, JsonRpcNotification, parse_jsonrpc,
)

if TYPE_CHECKING:
    from auraeve.bus.queue import MessageBus
    from auraeve.transports.acp.dispatcher import ACPDispatcher


class ACPConnectionHandler:
    """管理单个 WebSocket 连接的读写与总线订阅。"""

    def __init__(
        self,
        dispatcher: "ACPDispatcher",
        bus: "MessageBus",
        event_mapper: EventMapper,
    ) -> None:
        self._dispatcher = dispatcher
        self._bus = bus
        self._mapper = event_mapper
        self._ws: Any = None
        self._session_ids: set[str] = set()

    async def run(self, ws: Any) -> None:
        """主循环：持续读取 WebSocket 消息直到连接关闭。"""
        self._ws = ws
        logger.info("[acp] client connected")
        try:
            while True:
                try:
                    raw = await ws.receive_text()
                except Exception:
                    break
                await self._process_single_message(ws, raw)
        finally:
            self._cleanup()
            logger.info("[acp] client disconnected")

    async def _process_single_message(self, ws: Any, raw: str) -> None:
        msg = parse_jsonrpc(raw)
        result = await self._dispatcher.dispatch(msg)
        if result is None:
            return
        await ws.send_text(json.dumps(result.to_dict()))

    async def on_outbound(self, msg: OutboundMessage) -> None:
        """MessageBus 出站消息回调：翻译成 ACP 事件写回 WebSocket。"""
        if self._ws is None:
            return
        events = self._mapper.map(msg)
        for event in events:
            try:
                await self._ws.send_text(json.dumps(event))
            except Exception as exc:
                logger.warning(f"[acp] failed to send event: {exc}")

    def register_session(self, session_id: str) -> None:
        """订阅指定 session 的出站消息。"""
        channel = f"acp:{session_id}"
        self._session_ids.add(session_id)
        self._bus.subscribe_outbound(channel, self.on_outbound)

    def _cleanup(self) -> None:
        for session_id in self._session_ids:
            try:
                self._bus.unsubscribe_outbound(f"acp:{session_id}", self.on_outbound)
            except Exception:
                pass
        self._session_ids.clear()
        self._ws = None
