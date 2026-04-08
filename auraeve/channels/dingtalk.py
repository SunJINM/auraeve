"""钉钉渠道实现（Stream 模式）。支持文本、图片、语音、文件的收发。"""

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger
import httpx

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.bus.events import FileAttachment, OutboundMessage
from auraeve.channels.base import BaseChannel

try:
    from dingtalk_stream import (
        DingTalkStreamClient,
        Credential,
        CallbackHandler,
        CallbackMessage,
        AckMessage,
    )
    from dingtalk_stream.chatbot import ChatbotMessage

    DINGTALK_AVAILABLE = True
except ImportError:
    DINGTALK_AVAILABLE = False
    CallbackHandler = object  # type: ignore[assignment,misc]
    CallbackMessage = None    # type: ignore[assignment,misc]
    AckMessage = None         # type: ignore[assignment,misc]
    ChatbotMessage = None     # type: ignore[assignment,misc]


@dataclass
class DingTalkConfig:
    """钉钉渠道配置。"""
    client_id: str            # AppKey
    client_secret: str        # AppSecret
    allow_from: list[str] = field(default_factory=list)  # 白名单 staff_id，留空则允许所有人


class AureaDingTalkHandler(CallbackHandler):
    """钉钉 Stream SDK 回调处理器。"""

    def __init__(self, channel: "DingTalkChannel"):
        super().__init__()
        self.channel = channel

    async def process(self, message: CallbackMessage):
        try:
            chatbot_msg = ChatbotMessage.from_dict(message.data)
            sender_id = chatbot_msg.sender_staff_id or chatbot_msg.sender_id
            sender_name = chatbot_msg.sender_nick or "未知"

            logger.info(
                f"钉钉消息 来自 {sender_name}（{sender_id}）"
                f"，类型：{chatbot_msg.message_type}"
            )

            task = asyncio.create_task(
                self.channel._on_message(message.data, chatbot_msg, sender_id, sender_name)
            )
            self.channel._background_tasks.add(task)
            task.add_done_callback(self.channel._background_tasks.discard)

            return AckMessage.STATUS_OK, "OK"

        except Exception as e:
            logger.error(f"处理钉钉消息出错：{e}")
            return AckMessage.STATUS_OK, "Error"


class DingTalkChannel(BaseChannel):
    """
    钉钉渠道（Stream 模式）。

    接收：WebSocket 长连接（dingtalk-stream SDK）
    发送：HTTP API（batchSend 私信）
    支持：文本、图片（Vision）、语音（转录）、文件附件
    """

    name = "dingtalk"

    def __init__(
        self,
        config: DingTalkConfig,
        command_queue: RuntimeCommandQueue,
        workspace: Path | None = None,
    ):
        super().__init__(config, command_queue)
        self.config: DingTalkConfig = config
        self._client: Any = None
        self._http: httpx.AsyncClient | None = None
        self._access_token: str | None = None
        self._token_expiry: float = 0
        self._background_tasks: set[asyncio.Task] = set()

        # 媒体文件存储目录
        self._media_dir: Path | None = (workspace / "media") if workspace else None

        # 旧版 oapi.dingtalk.com 的 access_token（用于 media/upload）
        self._old_token: str | None = None
        self._old_token_expiry: float = 0

    # ── 启动 / 停止 ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """以 Stream 模式启动钉钉机器人。"""
        if not DINGTALK_AVAILABLE:
            logger.error("dingtalk-stream 未安装，请运行：pip install dingtalk-stream")
            return

        if not self.config.client_id or not self.config.client_secret:
            logger.error("钉钉 client_id 和 client_secret 未配置")
            return

        self._running = True
        self._http = httpx.AsyncClient(timeout=30.0)

        if self._media_dir:
            for sub in ("images", "voice", "files"):
                (self._media_dir / sub).mkdir(parents=True, exist_ok=True)

        logger.info(f"启动钉钉 Stream 客户端（AppKey: {self.config.client_id}）")
        credential = Credential(self.config.client_id, self.config.client_secret)
        self._client = DingTalkStreamClient(credential)

        handler = AureaDingTalkHandler(self)
        self._client.register_callback_handler(ChatbotMessage.TOPIC, handler)

        logger.info("钉钉 Stream 模式已启动")

        while self._running:
            try:
                await self._client.start()
            except Exception as e:
                logger.warning(f"钉钉 Stream 连接异常：{e}")
            if self._running:
                logger.info("5 秒后重新连接钉钉 Stream...")
                await asyncio.sleep(5)

    async def stop(self) -> None:
        self._running = False
        if self._http:
            await self._http.aclose()
            self._http = None
        for task in self._background_tasks:
            task.cancel()
        self._background_tasks.clear()

    # ── Token 管理 ───────────────────────────────────────────────────────

    async def _get_access_token(self) -> str | None:
        """获取或刷新钉钉访问令牌。"""
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        url = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
        data = {"appKey": self.config.client_id, "appSecret": self.config.client_secret}

        if not self._http:
            logger.warning("HTTP 客户端未初始化")
            return None

        try:
            resp = await self._http.post(url, json=data)
            resp.raise_for_status()
            res_data = resp.json()
            self._access_token = res_data.get("accessToken")
            self._token_expiry = time.time() + int(res_data.get("expireIn", 7200)) - 60
            return self._access_token
        except Exception as e:
            logger.error(f"获取钉钉访问令牌失败：{e}")
            return None

    async def _get_old_token(self) -> str | None:
        """获取旧版 oapi.dingtalk.com 的 access_token（用于 media/upload）。"""
        if self._old_token and time.time() < self._old_token_expiry:
            return self._old_token

        if not self._http:
            return None

        url = (
            f"https://oapi.dingtalk.com/gettoken"
            f"?appkey={self.config.client_id}&appsecret={self.config.client_secret}"
        )
        try:
            resp = await self._http.get(url)
            resp.raise_for_status()
            data = resp.json()
            if data.get("errcode", -1) != 0:
                logger.error(f"获取旧版钉钉 token 失败：{data}")
                return None
            self._old_token = data.get("access_token")
            self._old_token_expiry = time.time() + int(data.get("expires_in", 7200)) - 60
            return self._old_token
        except Exception as e:
            logger.error(f"获取旧版钉钉 token 出错：{e}")
            return None

    # ── 媒体下载 ─────────────────────────────────────────────────────────

    async def _download_media(self, download_code: str) -> bytes | None:
        """通过 downloadCode / mediaId 从钉钉下载媒体文件。"""
        token = await self._get_access_token()
        if not token or not self._http:
            return None

        try:
            url = "https://api.dingtalk.com/v1.0/robot/messageFiles/download"
            headers = {"x-acs-dingtalk-access-token": token}
            resp = await self._http.post(
                url,
                json={"downloadCode": download_code, "robotCode": self.config.client_id},
                headers=headers,
            )
            resp.raise_for_status()
            download_url = resp.json().get("downloadUrl")
            if not download_url:
                return None
            file_resp = await self._http.get(download_url)
            file_resp.raise_for_status()
            return file_resp.content
        except Exception as e:
            logger.error(f"下载媒体失败（code={download_code}）：{e}")
            return None

    async def _download_url(self, url: str) -> bytes | None:
        """直接从公开 URL 下载文件。"""
        if not self._http:
            return None
        try:
            resp = await self._http.get(url)
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            logger.error(f"下载 URL 失败（{url}）：{e}")
            return None

    # ── 媒体上传 ─────────────────────────────────────────────────────────

    async def _upload_media(self, file_path: str, media_type: str = "file") -> str | None:
        """将本地文件上传到钉钉，返回 media_id。

        使用旧版 oapi.dingtalk.com/media/upload 接口。
        media_type: "image" | "voice" | "video" | "file"
        """
        token = await self._get_old_token()
        if not token or not self._http:
            return None

        path = Path(file_path)
        if not path.exists():
            logger.error(f"上传文件不存在：{file_path}")
            return None

        url = f"https://oapi.dingtalk.com/media/upload?access_token={token}&type={media_type}"

        try:
            with open(path, "rb") as f:
                files = {"media": (path.name, f, _mime_for(path))}
                resp = await self._http.post(url, files=files)
            resp.raise_for_status()
            data = resp.json()
            if data.get("errcode", -1) != 0:
                logger.error(f"钉钉媒体上传失败：{data}")
                return None
            media_id = data.get("media_id")
            logger.info(f"文件上传完成：{path.name} → media_id={media_id}")
            return media_id
        except Exception as e:
            logger.error(f"上传媒体失败（{file_path}）：{e}")
            return None

    # ── 接收消息处理 ─────────────────────────────────────────────────────

    async def _on_message(
        self,
        raw_data: dict,
        chatbot_msg: Any,
        sender_id: str,
        sender_name: str,
    ) -> None:
        """根据消息类型分发处理。"""
        msg_type = chatbot_msg.message_type or raw_data.get("msgtype", "text")
        content = ""
        media: list[str] = []
        attachments: list[FileAttachment] = []

        try:
            if msg_type == "text":
                if chatbot_msg.text:
                    content = chatbot_msg.text.content.strip()
                else:
                    content = raw_data.get("text", {}).get("content", "").strip()

            elif msg_type == "picture":
                content, media = await self._recv_picture(raw_data, chatbot_msg)

            elif msg_type == "voice":
                content, voice_attachment = await self._recv_voice(raw_data, chatbot_msg)
                if voice_attachment:
                    attachments.append(voice_attachment)

            elif msg_type == "file":
                content = await self._recv_file(raw_data, chatbot_msg)

            elif msg_type == "richText":
                content = _extract_rich_text(raw_data, chatbot_msg)

            else:
                content = (
                    raw_data.get("text", {}).get("content", "")
                    or getattr(chatbot_msg, "content", "")
                    or ""
                ).strip()
                if not content:
                    logger.warning(f"未知消息类型 {msg_type}，已忽略")
                    return

        except Exception as e:
            logger.error(f"解析消息类型 {msg_type} 出错：{e}")
            content = "[消息解析失败]"

        if not content and not media:
            return

        try:
            await self._handle_message(
                sender_id=sender_id,
                chat_id=sender_id,
                content=content,
                media=media,
                attachments=attachments or None,
                metadata={"sender_name": sender_name, "platform": "dingtalk", "msg_type": msg_type},
            )
        except Exception as e:
            logger.error(f"发布钉钉消息出错：{e}")

    async def _recv_picture(
        self, raw_data: dict, chatbot_msg: Any
    ) -> tuple[str, list[str]]:
        """处理图片消息：下载保存，路径加入 media 列表供 LLM Vision 使用。"""
        content_data = _parse_content(raw_data, chatbot_msg)
        download_code = content_data.get("downloadCode", "")
        photo_url = content_data.get("photoURL", "")

        img_bytes = None
        if download_code:
            img_bytes = await self._download_media(download_code)
        if not img_bytes and photo_url:
            img_bytes = await self._download_url(photo_url)

        if img_bytes and self._media_dir:
            ts = int(time.time())
            img_path = self._media_dir / "images" / f"{ts}.jpg"
            img_path.write_bytes(img_bytes)
            logger.info(f"图片已保存：{img_path}（{len(img_bytes)} 字节）")
            return "[图片]", [str(img_path)]

        return "[图片消息]", []

    async def _recv_voice(self, raw_data: dict, chatbot_msg: Any) -> tuple[str, FileAttachment | None]:
        """处理语音消息：下载 AMR → 调用转录回调 → 返回文字。"""
        content_data = _parse_content(raw_data, chatbot_msg)
        media_id = content_data.get("mediaId", "")
        duration = content_data.get("duration", 0)

        if not media_id:
            return (f"[语音消息，时长 {duration} 秒]", None)

        audio_bytes = await self._download_media(media_id)
        if not audio_bytes:
            return (f"[语音消息，时长 {duration} 秒，下载失败]", None)

        audio_path: Path | None = None
        if self._media_dir:
            ts = int(time.time())
            audio_path = self._media_dir / "voice" / f"{ts}.amr"
            audio_path.write_bytes(audio_bytes)
            logger.info(f"语音已保存：{audio_path}（{duration}s，{len(audio_bytes)}B）")

        if audio_path:
            return (
                f"[语音消息（{duration}秒）]",
                FileAttachment(
                    filename=audio_path.name,
                    url=str(audio_path),
                    mime_type="audio/amr",
                    size=len(audio_bytes),
                ),
            )
        return (f"[语音消息，时长 {duration} 秒]", None)

    async def _recv_file(self, raw_data: dict, chatbot_msg: Any) -> str:
        """处理文件消息：下载保存，告知 Agent 文件路径。"""
        content_data = _parse_content(raw_data, chatbot_msg)
        download_code = content_data.get("downloadCode", "")
        file_name = content_data.get("fileName", f"file_{int(time.time())}")

        if not download_code:
            return f"[文件: {file_name}]"

        file_bytes = await self._download_media(download_code)
        if not file_bytes:
            return f"[文件: {file_name}，下载失败]"

        if self._media_dir:
            safe_name = re.sub(r"[^\w.\-]", "_", file_name)
            file_path = self._media_dir / "files" / f"{int(time.time())}_{safe_name}"
            file_path.write_bytes(file_bytes)
            logger.info(f"文件已保存：{file_path}（{len(file_bytes)} 字节）")
            return f"[文件: {file_name}，已保存至 {file_path}，可用 Read 读取内容]"

        return f"[文件: {file_name}，{len(file_bytes)} 字节，未保存（未配置工作区）]"

    # ── 发送消息 ─────────────────────────────────────────────────────────

    async def send(self, msg: OutboundMessage) -> None:
        """发送消息到钉钉。支持文本/Markdown、文件附件、图片 URL。"""
        token = await self._get_access_token()
        if not token:
            return

        # 优先级：本地文件附件 > 图片 URL > 文本/Markdown
        if msg.file_path:
            await self._send_file(msg, token)
            if msg.content:
                await asyncio.sleep(0.3)
                text_only = OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=msg.content)
                await self._send_markdown(text_only, token)
            return

        if msg.image_url:
            await self._send_image_url(msg, token)
            if msg.content:
                await asyncio.sleep(0.3)
                text_only = OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=msg.content)
                await self._send_markdown(text_only, token)
            return

        await self._send_markdown(msg, token)

    async def _send_markdown(self, msg: OutboundMessage, token: str) -> None:
        """发送 Markdown 文本消息。"""
        url = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
        headers = {"x-acs-dingtalk-access-token": token}
        data = {
            "robotCode": self.config.client_id,
            "userIds": [msg.chat_id],
            "msgKey": "sampleMarkdown",
            "msgParam": json.dumps({"text": msg.content, "title": "回复"}, ensure_ascii=False),
        }
        await self._do_send(url, headers, data, msg.chat_id)

    async def _send_file(self, msg: OutboundMessage, token: str) -> None:
        """发送本地文件。
        - voice → sampleAudio（上传后用 mediaId 发送）
        - video → sampleVideo（同上）
        - image → 钉钉单聊无直接图片上传 URL，降级发 Markdown 提示
        - file  → 钉钉单聊 batchSend 不支持 sampleFileMsg，降级发文件路径提示
        """
        path = Path(msg.file_path)
        suffix = path.suffix.lower()

        if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
            media_type = "image"
        elif suffix in {".mp4", ".avi", ".mov", ".mkv"}:
            media_type = "video"
        elif suffix in {".amr", ".mp3", ".wav", ".m4a", ".aac"}:
            media_type = "voice"
        else:
            media_type = "file"

        media_id = await self._upload_media(msg.file_path, media_type)
        if not media_id:
            fallback = msg.content or f"[文件发送失败: {path.name}]"
            await self._send_markdown(
                OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=fallback),
                token,
            )
            return

        if media_type == "voice":
            msg_key = "sampleAudio"
            msg_param: dict = {"mediaId": media_id, "duration": 0}
        elif media_type == "video":
            msg_key = "sampleVideo"
            msg_param = {"mediaId": media_id, "duration": 0, "videoMediaId": media_id}
        elif media_type == "image":
            # 图片使用 sampleImageMsg，需要先拿到可访问 URL；
            # 旧版上传后没有直接可访问 URL，退回 sampleMarkdown 提示
            fallback_text = msg.content or f"📎 图片文件：`{path.name}`（media_id: {media_id}）"
            await self._send_markdown(
                OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=fallback_text),
                token,
            )
            return
        else:
            # 钉钉单聊 batchSend 接口不支持 sampleFileMsg（仅群消息可用）。
            # 退回：发送文件名 + 本地路径，让用户知道文件已生成。
            file_size = path.stat().st_size if path.exists() else 0
            size_str = f"{file_size // 1024} KB" if file_size >= 1024 else f"{file_size} B"
            content_text = (
                f"📄 **{path.name}**（{size_str}）\n\n"
                f"文件已生成，路径：\n`{path}`\n\n"
                f"_钉钉单聊不支持直接发送文件附件，请在服务器上查看或通过其他方式获取。_"
            )
            if msg.content:
                content_text = msg.content + "\n\n" + content_text
            await self._send_markdown(
                OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=content_text),
                token,
            )
            return

        url = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
        headers = {"x-acs-dingtalk-access-token": token}
        data = {
            "robotCode": self.config.client_id,
            "userIds": [msg.chat_id],
            "msgKey": msg_key,
            "msgParam": json.dumps(msg_param, ensure_ascii=False),
        }
        await self._do_send(url, headers, data, msg.chat_id)

    async def _send_image_url(self, msg: OutboundMessage, token: str) -> None:
        """通过公开 URL 发送图片（sampleImageMsg）。"""
        url = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
        headers = {"x-acs-dingtalk-access-token": token}
        data = {
            "robotCode": self.config.client_id,
            "userIds": [msg.chat_id],
            "msgKey": "sampleImageMsg",
            "msgParam": json.dumps({"photoURL": msg.image_url}, ensure_ascii=False),
        }
        await self._do_send(url, headers, data, msg.chat_id)

    async def _do_send(self, url: str, headers: dict, data: dict, chat_id: str) -> None:
        """执行 HTTP 发送，统一处理错误。"""
        if not self._http:
            logger.warning("HTTP 客户端未初始化")
            return
        try:
            resp = await self._http.post(url, json=data, headers=headers)
            if resp.status_code != 200:
                logger.error(f"钉钉发送失败（{chat_id}）：{resp.text}")
            else:
                logger.debug(f"消息已发送至 {chat_id}")
        except Exception as e:
            logger.error(f"发送钉钉消息出错：{e}")


# ── 工具函数 ──────────────────────────────────────────────────────────────

def _parse_content(raw_data: dict, chatbot_msg: Any) -> dict:
    """解析消息 content 字段为 dict（针对 picture/voice/file 类型）。"""
    raw = getattr(chatbot_msg, "content", None) or raw_data.get("content", "")
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except Exception:
            pass
    if isinstance(raw, dict):
        return raw
    return {}


def _extract_rich_text(raw_data: dict, chatbot_msg: Any) -> str:
    """从富文本消息中提取所有文字内容。"""
    content_data = _parse_content(raw_data, chatbot_msg)
    rich_text = content_data.get("richText", [])
    parts = [item.get("text", "") for item in rich_text if isinstance(item, dict) and item.get("type") == "text"]
    return "\n".join(parts) if parts else (getattr(chatbot_msg, "content", "") or "")


def _mime_for(path: Path) -> str:
    """根据文件扩展名返回 MIME 类型。"""
    suffix = path.suffix.lower()
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
        ".amr": "audio/amr", ".mp3": "audio/mpeg",
        ".wav": "audio/wav", ".m4a": "audio/mp4", ".aac": "audio/aac",
        ".mp4": "video/mp4", ".avi": "video/x-msvideo",
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".zip": "application/zip",
    }.get(suffix, "application/octet-stream")
