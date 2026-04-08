"""出站消息分发器。"""

import asyncio
from typing import Callable, Awaitable

from loguru import logger

from auraeve.bus.events import OutboundMessage


class OutboundDispatcher:
    """
    仅负责出站消息分发。

    运行时入站已经统一收敛到 RuntimeCommandQueue；这里保留渠道侧的
    outbound 订阅与投递能力，避免把回复分发逻辑散落在各入口里。
    """

    def __init__(self):
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        self._outbound_subscribers: dict[str, list[Callable[[OutboundMessage], Awaitable[None]]]] = {}
        self._running = False

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
