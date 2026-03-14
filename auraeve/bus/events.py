"""消息总线的事件类型定义。"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class FileAttachment:
    """随消息携带的文件附件（对标 openclaw MediaAttachment）。"""
    filename: str           # 原始文件名
    url: str = ""           # 文件下载 URL（渠道提供）
    mime_type: str = ""     # 已知的 MIME 类型（可能不准，extract 时会重新嗅探）
    size: int = 0           # 文件大小（字节，0 表示未知）


@dataclass
class InboundMessage:
    """从聊天渠道接收到的消息。"""

    channel: str        # 渠道名称，如 dingtalk
    sender_id: str      # 发送者标识符
    chat_id: str        # 会话/聊天标识符
    content: str        # 消息文本内容
    timestamp: datetime = field(default_factory=datetime.now)
    media: list[str] = field(default_factory=list)
    attachments: list[FileAttachment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def session_key(self) -> str:
        """
        用于会话识别的唯一键。策略：身份优先 → channel:chat_id → sender_id。

        1. 优先 metadata.canonical_user_id（IdentityResolver 已写入时）
        2. 回退 channel:chat_id（渠道级别隔离）
        3. 最终回退 sender_id
        """
        canonical = self.metadata.get("canonical_user_id")
        if canonical:
            return canonical
        if self.chat_id:
            return f"{self.channel}:{self.chat_id}"
        return self.sender_id or "global"


@dataclass
class OutboundMessage:
    """待发送到聊天渠道的消息。"""

    channel: str
    chat_id: str
    content: str
    file_path: str | None = None   # 本地文件路径（上传后作为附件发送）
    image_url: str | None = None   # 公开图片 URL（直接嵌入发送）
    reply_to: str | None = None
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
