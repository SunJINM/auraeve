"""消息发送工具：向用户发送钉钉消息，支持文本、文件附件和图片。"""

from typing import Any, Callable, Awaitable

from auraeve.agent.tools.base import Tool
from auraeve.bus.events import OutboundMessage


class MessageTool(Tool):
    """向聊天渠道用户发送消息的工具，支持文本、文件附件和图片 URL。"""

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        default_channel: str = "",
        default_chat_id: str = "",
        channel_users: dict[str, str] | None = None,
        notify_channel: str = "",
    ):
        self._send_callback = send_callback
        self._default_channel = default_channel
        self._default_chat_id = default_chat_id
        # 各渠道主人的 chat_id 映射，如 {"dingtalk": "staff_id", "telegram": "123"}
        self._channel_users: dict[str, str] = channel_users or {}
        # 主动通知的首选渠道
        self._notify_channel = notify_channel
        # 直连发送回调（key=channel），错误可直接传回工具调用方 → LLM
        self._direct_senders: dict[str, Callable[[OutboundMessage], Awaitable[None]]] = {}

    def register_direct_sender(
        self, channel: str, sender: Callable[[OutboundMessage], Awaitable[None]]
    ) -> None:
        """注册某渠道的直连发送函数，绕过总线队列，错误可即时感知。"""
        self._direct_senders[channel] = sender

    def set_context(self, channel: str, chat_id: str) -> None:
        self._default_channel = channel
        self._default_chat_id = chat_id

    def _resolve_channel_chat_id(self, channel: str | None, chat_id: str | None) -> tuple[str, str]:
        """解析最终的 channel 和 chat_id。

        优先级：
        1. 明确传入的 channel + chat_id
        2. 传入渠道名但未传 chat_id → 从 channel_users 查主人 ID
        3. 都未传 → 使用当前会话上下文
        """
        resolved_channel = channel or self._default_channel
        if resolved_channel and not chat_id:
            # 尝试从 channel_users 查该渠道的主人 ID
            owner_id = self._channel_users.get(resolved_channel)
            if owner_id:
                return resolved_channel, owner_id
        resolved_chat_id = chat_id or self._default_chat_id
        return resolved_channel, resolved_chat_id

    @property
    def name(self) -> str:
        return "message"

    @property
    def description(self) -> str:
        channel_list = ", ".join(self._channel_users.keys()) if self._channel_users else "（未配置）"
        return (
            "向用户发送消息。支持纯文本/Markdown、本地文件附件（file_path）、"
            "图片公开 URL（image_url）。可组合使用：同时传 file_path 和 content 时，"
            "先发文件再发文字说明。\n"
            f"可用渠道名（channel 参数）：{channel_list}。"
            "指定渠道名但不传 chat_id 时，自动发给主人。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "消息文字内容（Markdown 格式），可与 file_path / image_url 同时使用"
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "可选：本地文件的绝对路径，上传后作为附件发送。"
                        "支持图片（jpg/png/gif）、音频（mp3/wav/amr）、"
                        "视频（mp4）、文档（pdf/docx/xlsx）等。"
                    )
                },
                "image_url": {
                    "type": "string",
                    "description": "可选：公开图片 URL，直接嵌入发送（无需上传）"
                },
                "channel": {
                    "type": "string",
                    "description": "可选：目标渠道（默认当前会话渠道）"
                },
                "chat_id": {
                    "type": "string",
                    "description": "可选：目标聊天/用户 ID（默认当前会话 ID）"
                },
            },
            "required": ["content"]
        }

    async def execute(
        self,
        content: str,
        file_path: str | None = None,
        image_url: str | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        **kwargs: Any
    ) -> str:
        channel, chat_id = self._resolve_channel_chat_id(channel, chat_id)

        if not channel or not chat_id:
            return "错误：未指定目标渠道/聊天"
        if not self._send_callback:
            return "错误：消息发送未配置"

        msg = OutboundMessage(
            channel=channel,
            chat_id=chat_id,
            content=content,
            file_path=file_path or None,
            image_url=image_url or None,
        )
        direct_sender = self._direct_senders.get(channel)
        try:
            if direct_sender:
                # 直连发送：同步等待结果，错误会直接抛出并返回给 LLM
                await direct_sender(msg)
            else:
                # 总线发送：异步投递，不感知发送结果（兜底）
                await self._send_callback(msg)
            parts = [f"消息已发送至 {channel}:{chat_id}"]
            if file_path:
                parts.append(f"文件：{file_path}")
            if image_url:
                parts.append(f"图片：{image_url}")
            return "，".join(parts)
        except Exception as e:
            return f"发送消息出错：{str(e)}"
