"""NapCat channel implementation (OneBot v11 over WebSocket)."""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.bus.events import FileAttachment, OutboundMessage
from auraeve.channels.base import BaseChannel

try:
    import websockets

    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False


@dataclass
class NapCatConfig:
    ws_url: str = "ws://127.0.0.1:3001"
    access_token: str = ""
    allow_from: list[str] = field(default_factory=list)
    allow_groups: list[str] = field(default_factory=list)
    reconnect_interval: int = 5
    action_timeout_s: float = 10.0
    media_action_timeout_s: float = 30.0
    media_action_retries: int = 1


@dataclass
class MediaRef:
    kind: str
    filename: str
    mime_type: str
    url: str = ""
    file_token: str = ""
    size: int = 0


@dataclass
class ParsedMessage:
    text: str
    image_urls: list[str]
    refs: list[MediaRef]


class NapCatChannel(BaseChannel):
    name = "napcat"

    _UNRESOLVED_PREFIX = "__napcat_unresolved__:"
    _FILE_ID_PREFIX = "__file_id__:"
    _IMAGE_FILE_PREFIX = "__image_file__:"
    _RECORD_FILE_PREFIX = "__record_file__:"

    _FACE_NAMES: dict[str, str] = {
        "14": "微笑",
        "1": "撇嘴",
        "2": "色",
        "3": "发呆",
        "4": "得意",
        "5": "流泪",
        "6": "害羞",
        "9": "大哭",
        "10": "尴尬",
        "11": "发怒",
        "12": "调皮",
        "13": "龇牙",
        "16": "酷",
        "19": "吐",
        "21": "可爱",
        "30": "奋斗",
        "66": "爱心",
        "74": "太阳",
        "75": "月亮",
        "76": "赞",
        "77": "踩",
        "179": "doge",
        "212": "点赞",
    }

    def __init__(self, config: NapCatConfig, command_queue: RuntimeCommandQueue):
        super().__init__(config, command_queue)
        self.config: NapCatConfig = config
        self._ws = None
        self._task: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._friend_flags: dict[str, str] = {}

    async def start(self) -> None:
        if not WEBSOCKETS_AVAILABLE:
            logger.error("NapCat channel requires websockets: pip install websockets")
            return
        self._running = True
        self._task = asyncio.create_task(self._connect_loop())
        await self._task

    async def stop(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._task and not self._task.done():
            self._task.cancel()

    async def send(self, msg: OutboundMessage) -> None:
        if not self._ws:
            logger.warning("NapCat WS is not connected, skip outbound message")
            return
        if msg.chat_id.startswith("group:"):
            await self._send_group_msg(msg.chat_id[6:], msg)
            return
        user_id = msg.chat_id[8:] if msg.chat_id.startswith("private:") else msg.chat_id
        await self._send_private_msg(user_id, msg)

    def _build_message_segments(self, msg: OutboundMessage) -> list[dict]:
        segments: list[dict] = []
        if msg.image_url:
            segments.append({"type": "image", "data": {"file": msg.image_url}})
        if msg.file_path:
            mime, _ = mimetypes.guess_type(msg.file_path)
            ext = Path(msg.file_path).suffix.lower()
            if mime and mime.startswith("image/"):
                b64_uri = self._encode_file_as_base64_uri(msg.file_path)
                segments.append({"type": "image", "data": {"file": b64_uri}})
            elif (mime and mime.startswith("audio/")) or ext in {".mp3", ".wav", ".ogg", ".amr", ".silk", ".m4a"}:
                b64_uri = self._encode_file_as_base64_uri(msg.file_path)
                segments.append({"type": "record", "data": {"file": b64_uri}})
                return segments
        if msg.content:
            segments.append({"type": "text", "data": {"text": msg.content}})
        return segments

    async def _send_private_msg(self, user_id: str, msg: OutboundMessage) -> None:
        await self._send_binary_if_needed(
            chat_kind="private",
            target_id=user_id,
            file_path=msg.file_path,
        )
        segments = self._build_message_segments(msg)
        if segments:
            await self._call_action(
                "send_private_msg",
                {"user_id": int(user_id), "message": segments},
            )

    async def _send_group_msg(self, group_id: str, msg: OutboundMessage) -> None:
        await self._send_binary_if_needed(
            chat_kind="group",
            target_id=group_id,
            file_path=msg.file_path,
        )
        segments = self._build_message_segments(msg)
        if segments:
            await self._call_action(
                "send_group_msg",
                {"group_id": int(group_id), "message": segments},
            )

    async def _send_binary_if_needed(self, *, chat_kind: str, target_id: str, file_path: str | None) -> None:
        if not file_path:
            return
        mime, _ = mimetypes.guess_type(file_path)
        ext = Path(file_path).suffix.lower()
        is_audio = (mime and mime.startswith("audio/")) or ext in {".mp3", ".wav", ".ogg", ".amr", ".silk", ".m4a"}
        is_image = bool(mime and mime.startswith("image/"))
        if is_audio or is_image:
            return
        b64_uri = self._encode_file_as_base64_uri(file_path)
        file_name = Path(file_path).name
        if chat_kind == "private":
            await self._call_action(
                "upload_private_file",
                {"user_id": int(target_id), "file": b64_uri, "name": file_name},
            )
        else:
            await self._call_action(
                "upload_group_file",
                {"group_id": int(target_id), "file": b64_uri, "name": file_name},
            )

    @staticmethod
    def _encode_file_as_base64_uri(file_path: str) -> str:
        with open(file_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f"base64://{b64}"

    def _timeout_for_action(self, action: str) -> float:
        if action in {"get_image", "get_file", "get_record"}:
            return float(self.config.media_action_timeout_s)
        return float(self.config.action_timeout_s)

    async def _call_action(self, action: str, params: dict, *, timeout_s: float | None = None) -> dict | None:
        if not self._ws:
            return None
        echo = str(uuid.uuid4())
        payload = {"action": action, "params": params, "echo": echo}
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[echo] = future
        timeout = timeout_s if timeout_s is not None else self._timeout_for_action(action)
        try:
            await self._ws.send(json.dumps(payload, ensure_ascii=False))
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"NapCat action timeout: {action} ({timeout:.1f}s)")
            return None
        finally:
            self._pending.pop(echo, None)

    async def _call_action_with_retry(self, action: str, params: dict) -> dict | None:
        retries = max(0, int(self.config.media_action_retries))
        for attempt in range(retries + 1):
            result = await self._call_action(action, params)
            if result:
                return result
            if attempt < retries:
                await asyncio.sleep(0.5 * (attempt + 1))
        return None

    async def _connect_loop(self) -> None:
        while self._running:
            try:
                await self._run_ws()
            except Exception as exc:
                if self._running:
                    logger.warning(
                        f"NapCat WS disconnected: {type(exc).__name__}: {exc}, reconnect in {self.config.reconnect_interval}s"
                    )
                    await asyncio.sleep(self.config.reconnect_interval)

    async def _run_ws(self) -> None:
        headers = {}
        if self.config.access_token:
            headers["Authorization"] = f"Bearer {self.config.access_token}"
        logger.info(f"NapCat connecting: {self.config.ws_url}")
        async with websockets.connect(self.config.ws_url, additional_headers=headers) as ws:
            self._ws = ws
            logger.info("NapCat WS connected")
            async for raw in ws:
                try:
                    data = json.loads(raw)
                    await self._dispatch(data)
                except Exception as exc:
                    logger.error(f"NapCat dispatch error: {exc}")
        self._ws = None

    async def _dispatch(self, data: dict) -> None:
        if "echo" in data and data["echo"] in self._pending:
            future = self._pending[data["echo"]]
            if not future.done():
                future.set_result(data.get("data"))
            return

        post_type = data.get("post_type")
        if post_type == "request" and data.get("request_type") == "friend":
            await self._dispatch_friend_request(data)
            return
        if post_type != "message":
            return

        message_type = str(data.get("message_type", ""))
        user_id = str(data.get("user_id", ""))
        if message_type == "private":
            await self._dispatch_private_message(data, user_id)
            return
        if message_type == "group":
            await self._dispatch_group_message(data, user_id)

    async def _dispatch_friend_request(self, data: dict) -> None:
        user_id = str(data.get("user_id", ""))
        comment = str(data.get("comment", ""))
        flag = str(data.get("flag", ""))
        if flag:
            self._friend_flags[user_id] = flag
        content = "[系统] 该用户正在申请加好友"
        if comment:
            content += f"，验证消息：{comment}"
        content += f"\n\n可通过 napcat_friend_request 处理（flag={flag}）。"
        await self._handle_message(
            sender_id=user_id,
            chat_id=f"private:{user_id}",
            content=content,
            metadata={"system_event": "friend_request", "flag": flag, "from_qq": user_id},
        )

    async def _dispatch_private_message(self, data: dict, user_id: str) -> None:
        if not self.is_allowed(user_id):
            logger.warning(f"NapCat blocked private message from: {user_id}")
            return
        parsed = self._parse_message_segments(data.get("message", []))
        attachments = await self._resolve_media_refs(parsed.refs)
        content = self._build_content(parsed.text, parsed.image_urls, attachments)
        if not content and not parsed.image_urls and not attachments:
            return
        metadata: dict[str, Any] = {
            "message_type": "private",
            "qq": user_id,
        }
        if self._friend_flags:
            metadata["pending_friend_requests"] = [
                {"qq": qq, "flag": flag} for qq, flag in self._friend_flags.items()
            ]
        logger.info(
            f"NapCat private from {user_id}: {(content or '')[:50]}"
            + (f", attachments={len(attachments)}" if attachments else "")
        )
        await self._handle_message(
            sender_id=user_id,
            chat_id=f"private:{user_id}",
            content=content,
            media=None,
            attachments=attachments or None,
            metadata=metadata,
        )

    async def _dispatch_group_message(self, data: dict, user_id: str) -> None:
        group_id = str(data.get("group_id", ""))
        if self.config.allow_groups and group_id not in self.config.allow_groups:
            return
        segments = data.get("message") or []
        at_me = any(
            isinstance(seg, dict)
            and seg.get("type") == "at"
            and str(seg.get("data", {}).get("qq")) == str(data.get("self_id", ""))
            for seg in segments
        )
        if not at_me:
            return
        parsed = self._parse_message_segments(segments, skip_at=True)
        attachments = await self._resolve_media_refs(parsed.refs)
        content = self._build_content(parsed.text.strip(), parsed.image_urls, attachments)
        if not content and not parsed.image_urls and not attachments:
            return
        logger.info(
            f"NapCat group {group_id} from {user_id}: {(content or '')[:50]}"
            + (f", attachments={len(attachments)}" if attachments else "")
        )
        await self._handle_message(
            sender_id=user_id,
            chat_id=f"group:{group_id}",
            content=content,
            media=None,
            attachments=attachments or None,
            metadata={
                "message_type": "group",
                "group_id": group_id,
                "qq": user_id,
                "at_me": at_me,
            },
        )

    def _build_content(
        self,
        text: str,
        image_urls: list[str],
        attachments: list[FileAttachment],
    ) -> str:
        if any((att.mime_type or "").lower().startswith("audio/") for att in attachments):
            return "[语音]"
        if text:
            return text
        if image_urls:
            return "[图片]"
        if any((att.mime_type or "").lower().startswith("image/") for att in attachments):
            return "[图片]"
        if attachments:
            return "[附件]"
        return ""
    @staticmethod
    def _is_http_url(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        s = value.strip().lower()
        return s.startswith("http://") or s.startswith("https://")

    @staticmethod
    def _looks_like_local_path(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        s = value.strip()
        if not s:
            return False
        if s.lower().startswith("file://"):
            return True
        if s.startswith("/") or s.startswith("\\"):
            return True
        return len(s) >= 3 and s[1:3] == ":\\"

    @staticmethod
    def _extract_filename(raw: str, default: str) -> str:
        if not isinstance(raw, str) or not raw.strip():
            return default
        candidate = raw.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return candidate.strip() or default

    @staticmethod
    def _coerce_int(value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 0

    def _extract_content(
        self, segments: list, skip_at: bool = False
    ) -> tuple[str, list[str], list[FileAttachment]]:
        parsed = self._parse_message_segments(segments, skip_at=skip_at)
        attachments = [self._ref_to_placeholder_attachment(item) for item in parsed.refs]
        return parsed.text, parsed.image_urls, attachments

    def _parse_message_segments(self, segments: list, skip_at: bool = False) -> ParsedMessage:
        parts: list[str] = []
        image_urls: list[str] = []
        refs: list[MediaRef] = []
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            seg_type = str(seg.get("type", "")).strip()
            data = seg.get("data", {}) or {}
            if seg_type == "text":
                parts.append(str(data.get("text", "")))
                continue
            if seg_type == "at" and not skip_at:
                parts.append(f"@{data.get('qq', '')}")
                continue
            if seg_type == "face":
                face_id = str(data.get("id", ""))
                parts.append(f"[{self._FACE_NAMES.get(face_id, '表情')}]")
                continue
            if seg_type == "mface":
                summary = str(data.get("summary", "")).strip()
                parts.append(f"[{summary.strip('[]') if summary else '动态表情'}]")
                continue
            if seg_type == "image":
                ref = self._build_image_ref(data)
                if ref:
                    refs.append(ref)
                    if self._is_http_url(ref.url):
                        image_urls.append(ref.url)
                else:
                    parts.append("[图片]")
                continue
            if seg_type == "record":
                ref = self._build_record_ref(data)
                if ref:
                    refs.append(ref)
                parts.append("[语音]")
                continue
            if seg_type == "video":
                ref = self._build_video_ref(data)
                if ref:
                    refs.append(ref)
                else:
                    parts.append("[视频]")
                continue
            if seg_type == "file":
                ref = self._build_file_ref(data)
                if ref:
                    refs.append(ref)
                else:
                    parts.append("[文件]")
        return ParsedMessage(text="".join(parts), image_urls=image_urls, refs=refs)

    def _build_image_ref(self, data: dict[str, Any]) -> MediaRef | None:
        url = str(data.get("url", "")).strip()
        raw_file = str(data.get("file", "")).strip()
        token = ""
        if raw_file and not self._is_http_url(raw_file) and not self._looks_like_local_path(raw_file):
            token = raw_file
        elif not url and self._is_http_url(raw_file):
            url = raw_file
        elif not url and self._looks_like_local_path(raw_file):
            url = raw_file
        if not url and not token:
            return None
        filename = self._extract_filename(raw_file or url, "image")
        return MediaRef(kind="image", filename=filename, mime_type="image/*", url=url, file_token=token)

    def _build_record_ref(self, data: dict[str, Any]) -> MediaRef | None:
        url = str(data.get("url", "")).strip()
        raw_file = str(data.get("file", "")).strip()
        token = ""
        if not url and self._is_http_url(raw_file):
            url = raw_file
        elif not url and self._looks_like_local_path(raw_file):
            url = raw_file
        elif raw_file:
            token = raw_file
        if not url and not token:
            return None
        filename = self._extract_filename(raw_file or url, "voice")
        return MediaRef(kind="record", filename=filename, mime_type="audio/*", url=url, file_token=token)

    def _build_video_ref(self, data: dict[str, Any]) -> MediaRef | None:
        url = str(data.get("url", "")).strip()
        raw_file = str(data.get("file", "")).strip()
        token = ""
        if not url and self._is_http_url(raw_file):
            url = raw_file
        elif not url and self._looks_like_local_path(raw_file):
            url = raw_file
        elif raw_file:
            token = raw_file
        if not url and not token:
            return None
        filename = self._extract_filename(raw_file or url, "video.mp4")
        return MediaRef(kind="video", filename=filename, mime_type="video/mp4", url=url, file_token=token)

    def _build_file_ref(self, data: dict[str, Any]) -> MediaRef | None:
        url = str(data.get("url", "")).strip()
        raw_file = str(data.get("file", "")).strip()
        file_id = str(data.get("file_id", "")).strip()
        if not url and self._is_http_url(raw_file):
            url = raw_file
        elif not url and self._looks_like_local_path(raw_file):
            url = raw_file
        if not file_id and raw_file and not url and not self._looks_like_local_path(raw_file):
            file_id = raw_file
        filename_raw = str(data.get("name", "") or data.get("file_name", "") or raw_file)
        filename = self._extract_filename(filename_raw, "file")
        size = self._coerce_int(data.get("file_size", 0))
        if not url and not file_id:
            return None
        return MediaRef(kind="file", filename=filename, mime_type="", url=url, file_token=file_id, size=size)

    def _ref_to_placeholder_attachment(self, ref: MediaRef) -> FileAttachment:
        marker = ""
        if ref.kind == "image" and ref.file_token:
            marker = f"{self._IMAGE_FILE_PREFIX}{ref.file_token}"
        elif ref.kind == "record" and ref.file_token:
            marker = f"{self._RECORD_FILE_PREFIX}{ref.file_token}"
        elif ref.kind in {"file", "video"} and ref.file_token:
            marker = f"{self._FILE_ID_PREFIX}{ref.file_token}"
        return FileAttachment(
            filename=ref.filename,
            url=marker or ref.url,
            mime_type=ref.mime_type,
            size=ref.size,
        )

    async def _resolve_file_attachments(self, attachments: list[FileAttachment]) -> list[FileAttachment]:
        refs: list[MediaRef] = []
        for att in attachments:
            url = att.url or ""
            if url.startswith(self._IMAGE_FILE_PREFIX):
                refs.append(
                    MediaRef(
                        kind="image",
                        filename=att.filename,
                        mime_type=att.mime_type or "image/*",
                        file_token=url[len(self._IMAGE_FILE_PREFIX) :],
                        size=att.size,
                    )
                )
                continue
            if url.startswith(self._RECORD_FILE_PREFIX):
                refs.append(
                    MediaRef(
                        kind="record",
                        filename=att.filename,
                        mime_type=att.mime_type or "audio/*",
                        file_token=url[len(self._RECORD_FILE_PREFIX) :],
                        size=att.size,
                    )
                )
                continue
            if url.startswith(self._FILE_ID_PREFIX):
                refs.append(
                    MediaRef(
                        kind="file",
                        filename=att.filename,
                        mime_type=att.mime_type,
                        file_token=url[len(self._FILE_ID_PREFIX) :],
                        size=att.size,
                    )
                )
                continue
            refs.append(
                MediaRef(
                    kind="file" if not (att.mime_type or "").startswith("image/") else "image",
                    filename=att.filename,
                    mime_type=att.mime_type,
                    url=att.url,
                    size=att.size,
                )
            )
        return await self._resolve_media_refs(refs)

    async def _resolve_media_refs(self, refs: list[MediaRef]) -> list[FileAttachment]:
        resolved: list[FileAttachment] = []
        for ref in refs:
            resolved_url = await self._resolve_media_ref_url(ref)
            if not resolved_url and ref.url:
                resolved_url = ref.url
            if not resolved_url and ref.file_token:
                resolved_url = f"{self._UNRESOLVED_PREFIX}{ref.kind}:{ref.file_token}"
            if not resolved_url:
                continue
            resolved.append(
                FileAttachment(
                    filename=ref.filename,
                    url=resolved_url,
                    mime_type=ref.mime_type,
                    size=ref.size,
                )
            )
        return resolved

    async def _resolve_media_ref_url(self, ref: MediaRef) -> str:
        if ref.url and (self._is_http_url(ref.url) or self._looks_like_local_path(ref.url)):
            return ref.url
        if not ref.file_token:
            return ""
        if ref.kind == "image":
            result = await self._call_action_with_retry("get_image", {"file": ref.file_token})
            data = result or {}
            return str(data.get("url") or data.get("file") or data.get("path") or "").strip()
        if ref.kind == "record":
            result = await self._call_action_with_retry(
                "get_record",
                {"file": ref.file_token, "out_format": "mp3"},
            )
            data = result or {}
            return str(data.get("url") or data.get("file") or data.get("path") or "").strip()
        if ref.kind in {"file", "video"}:
            result = await self._call_action_with_retry("get_file", {"file_id": ref.file_token})
            data = result or {}
            return str(data.get("url") or data.get("file") or data.get("path") or "").strip()
        return ""


