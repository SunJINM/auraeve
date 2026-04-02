"""聊天平台渠道的抽象基类。"""

from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.agent_runtime.command_types import QueuedCommand
from auraeve.bus.events import FileAttachment, OutboundMessage


class BaseChannel(ABC):
    """聊天渠道实现的抽象基类。"""

    name: str = "base"

    def __init__(self, config: Any, command_queue: RuntimeCommandQueue):
        self.config = config
        self.command_queue = command_queue
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        pass

    def is_allowed(self, sender_id: str) -> bool:
        """检查发送者是否在白名单中（白名单为空则允许所有人）。"""
        allow_list = getattr(self.config, "allow_from", [])
        if not allow_list:
            return True
        sender_str = str(sender_id)
        if sender_str in allow_list:
            return True
        if "|" in sender_str:
            for part in sender_str.split("|"):
                if part and part in allow_list:
                    return True
        return False

    async def _handle_message(
        self,
        sender_id: str,
        chat_id: str,
        content: str,
        media: list[str] | None = None,
        attachments: list[FileAttachment] | None = None,
        metadata: dict[str, Any] | None = None
    ) -> None:
        if not self.is_allowed(sender_id):
            logger.warning(
                f"{self.name} 拒绝访问：{sender_id}，"
                f"如需开放权限请将其添加到配置文件的 allow_from 列表。"
            )
            return

        self.command_queue.enqueue_command(
            QueuedCommand(
                session_key=f"{self.name}:{chat_id}",
                source=self.name,
                mode="prompt",
                priority="next",
                payload={
                    "content": content,
                    "channel": self.name,
                    "sender_id": str(sender_id),
                    "chat_id": str(chat_id),
                    "media": media or [],
                    "attachments": attachments or [],
                    "metadata": metadata or {},
                },
                origin={"kind": "user"},
            )
        )

    @property
    def is_running(self) -> bool:
        return self._running
