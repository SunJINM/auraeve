"""异步消息队列，解耦渠道与 Agent 核心的通信。"""

import asyncio
from typing import Callable, Awaitable

from loguru import logger

from auraeve.bus.events import InboundMessage, OutboundMessage


class MessageBus:
    """
    异步消息总线，将聊天渠道与 Agent 核心解耦。

    渠道将消息推入入站队列，Agent 处理后将响应推入出站队列。
    """

    def __init__(self):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        self._outbound_subscribers: dict[str, list[Callable[[OutboundMessage], Awaitable[None]]]] = {}
        self._running = False

    async def publish_inbound(self, msg: InboundMessage) -> None:
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        await self.outbound.put(msg)

    async def consume_outbound(self) -> OutboundMessage:
        return await self.outbound.get()

    def subscribe_outbound(
        self,
        channel: str,
        callback: Callable[[OutboundMessage], Awaitable[None]]
    ) -> None:
        """订阅指定渠道的出站消息。"""
        if channel not in self._outbound_subscribers:
            self._outbound_subscribers[channel] = []
        self._outbound_subscribers[channel].append(callback)

    def unsubscribe_outbound(
        self,
        channel: str,
        callback: Callable[[OutboundMessage], Awaitable[None]],
    ) -> None:
        subscribers = self._outbound_subscribers.get(channel)
        if not subscribers:
            return
        self._outbound_subscribers[channel] = [item for item in subscribers if item != callback]

    async def dispatch_outbound(self) -> None:
        """将出站消息分发给已订阅的渠道，作为后台任务运行。"""
        self._running = True
        while self._running:
            try:
                msg = await asyncio.wait_for(self.outbound.get(), timeout=1.0)
                subscribers = self._outbound_subscribers.get(msg.channel, [])
                for callback in subscribers:
                    try:
                        await callback(msg)
                    except Exception as e:
                        logger.error(f"分发消息到 {msg.channel} 失败: {e}")
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        self._running = False
