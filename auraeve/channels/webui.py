"""WebUI 渠道：将 Agent 回复推送到 ChatService。"""
from __future__ import annotations

from dataclasses import dataclass, field

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.bus.events import OutboundMessage
from auraeve.channels.base import BaseChannel


@dataclass
class WebUIChannelConfig:
    allow_from: list[str] = field(default_factory=list)


class WebUIChannel(BaseChannel):
    """
    WebUI 渠道。

    入站：ChatService.send() 通过 RuntimeCommandQueue.enqueue_command() 注入消息。
    出站：Bus 分发 OutboundMessage 给本渠道 -> 转发给 ChatService.on_outbound()。
    """

    name = "webui"

    def __init__(
        self,
        config: WebUIChannelConfig,
        command_queue: RuntimeCommandQueue,
        chat_service,
    ) -> None:
        super().__init__(config, command_queue)
        self._chat_service = chat_service

    async def start(self) -> None:
        self._running = True
        # WebUI 渠道无需主动轮询，生命周期由 WebUIServer 管理
        # 此方法保持协程语义即可
        import asyncio
        while self._running:
            await asyncio.sleep(3600)

    async def stop(self) -> None:
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        """将 Agent 回复转发给 ChatService（进而广播给 SSE 订阅者）。"""
        await self._chat_service.on_outbound(msg)
