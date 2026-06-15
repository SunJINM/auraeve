"""图片产物存储：将生成/返回的图片落盘，对外只暴露短引用。

设计目标（对应需求3）：
- 图片二进制只存磁盘（state_dir/media/），绝不进入对话上下文或 SSE 负载。
- 消息历史与前端只携带短引用 {id, url, mime}，url 指向 WebUI 的 /api/webui/media/{id}。
- 统一解析三种来源：chat 响应的 message.images / delta.images（data URL）、
  images.generate 的 b64_json、以及外链 http(s) URL。
"""

from __future__ import annotations

import base64
import re
import uuid
from pathlib import Path
from typing import Any

from auraeve.config.paths import resolve_media_dir

_EXT_BY_MIME: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

_DATA_URL_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$", re.S)


def media_dir() -> Path:
    d = resolve_media_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def media_url(image_id: str) -> str:
    return f"/api/webui/media/{image_id}"


def save_image_bytes(data: bytes, mime: str = "image/png") -> dict[str, str]:
    ext = _EXT_BY_MIME.get((mime or "").lower(), ".png")
    image_id = f"img_{uuid.uuid4().hex}{ext}"
    (media_dir() / image_id).write_bytes(data)
    return {"id": image_id, "url": media_url(image_id), "mime": mime or "image/png"}


def save_image_b64(b64: str, mime: str = "image/png") -> dict[str, str]:
    raw = base64.b64decode("".join((b64 or "").split()))
    return save_image_bytes(raw, mime)


def save_data_url(data_url: str) -> dict[str, str] | None:
    m = _DATA_URL_RE.match((data_url or "").strip())
    if not m:
        return None
    return save_image_b64(m.group("data"), m.group("mime"))


def resolve_media_path(image_id: str) -> Path | None:
    """按 id 解析磁盘路径，仅取文件名以防目录穿越。"""
    name = Path(str(image_id)).name
    if not name:
        return None
    p = media_dir() / name
    return p if p.is_file() else None


def _url_from_image_item(item: Any) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        image_url = item.get("image_url")
        if isinstance(image_url, dict) and isinstance(image_url.get("url"), str):
            return image_url["url"]
        if isinstance(image_url, str):
            return image_url
        if isinstance(item.get("url"), str):
            return item["url"]
    return None


def compress_for_upload(
    path: Path,
    *,
    max_side: int = 1024,
    max_bytes: int = 900_000,
) -> tuple[bytes, str, str]:
    """压缩图片用于编辑上传，避免原图过大触发网关 413。

    长边缩放到 max_side；优先 PNG，超出 max_bytes 时改用递减质量的 JPEG。
    返回 (二进制数据, 文件名, mime)。
    """
    import io

    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))

        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
        if len(data) <= max_bytes:
            return data, "image.png", "image/png"

        for quality in (90, 80, 70, 60, 50):
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            if len(data) <= max_bytes:
                return data, "image.jpg", "image/jpeg"
        return data, "image.jpg", "image/jpeg"


def refs_from_images_field(images: Any, *, alt: str = "", prompt: str = "") -> list[dict[str, str]]:
    """解析 chat 响应的 images 字段（message.images / delta.images）并落盘，返回引用列表。

    支持项形态：data URL 字符串、{image_url:{url}}、{url}、{b64_json,mime}、http(s) 外链。
    """
    refs: list[dict[str, str]] = []
    for item in images or []:
        if isinstance(item, dict) and isinstance(item.get("b64_json"), str):
            ref = save_image_b64(item["b64_json"], item.get("mime") or "image/png")
        else:
            url = _url_from_image_item(item)
            if not isinstance(url, str) or not url:
                continue
            if url.startswith("data:"):
                ref = save_data_url(url)
                if ref is None:
                    continue
            elif url.startswith("http://") or url.startswith("https://"):
                ref = {"id": "", "url": url, "mime": "image/*"}
            else:
                continue
        if alt:
            ref["alt"] = alt
        if prompt:
            ref["prompt"] = prompt
        refs.append(ref)
    return refs
