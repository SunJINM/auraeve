"""统一资源产物存储。

资源二进制保存在 state_dir/resources 下，运行时与工具之间使用 media://id 作为稳定引用；
WebUI 展示时再转换为 /api/webui/resources/{id}/content。
"""

from __future__ import annotations

import base64
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from auraeve.config.paths import resolve_resources_dir

_EXT_BY_MIME: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_KIND_DIR: dict[str, str] = {
    "image": "images",
    "audio": "audio",
    "file": "files",
}
_DATA_URL_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$", re.S)


def resources_dir() -> Path:
    path = resolve_resources_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_ref(resource_id: str) -> str:
    return f"media://{Path(str(resource_id)).name}"


def resource_content_url(resource_id: str) -> str:
    return f"/api/webui/resources/{Path(str(resource_id)).name}/content"


def resource_download_url(resource_id: str) -> str:
    return f"/api/webui/resources/{Path(str(resource_id)).name}/download"


def _index_path() -> Path:
    return resources_dir() / "index.json"


def _read_index() -> dict[str, dict[str, Any]]:
    path = _index_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_index(index: dict[str, dict[str, Any]]) -> None:
    _index_path().write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _kind_dir(kind: str) -> Path:
    folder = _KIND_DIR.get(kind, "files")
    path = resources_dir() / folder
    path.mkdir(parents=True, exist_ok=True)
    return path


def _normalize_resource_id(value: str) -> str:
    raw = str(value or "").strip()
    if raw.startswith("media://"):
        raw = raw[len("media://") :]
    elif "/api/webui/resources/" in raw:
        raw = raw.split("/api/webui/resources/", 1)[1].split("/", 1)[0]
    return Path(raw).name


def _build_ref(
    *,
    resource_id: str,
    kind: str,
    mime: str,
    filename: str,
    source: str = "",
    prompt: str = "",
    alt: str = "",
    tool_call_id: str = "",
    session_key: str = "",
) -> dict[str, str]:
    ref = {
        "id": resource_id,
        "ref": resource_ref(resource_id),
        "kind": kind,
        "mime": mime,
        "filename": filename,
        "url": resource_content_url(resource_id),
        "displayUrl": resource_content_url(resource_id),
        "downloadUrl": resource_download_url(resource_id),
    }
    if source:
        ref["source"] = source
    if prompt:
        ref["prompt"] = prompt
    if alt:
        ref["alt"] = alt
    if tool_call_id:
        ref["toolCallId"] = tool_call_id
    if session_key:
        ref["sessionKey"] = session_key
    return ref


def save_bytes(
    data: bytes,
    *,
    kind: str = "file",
    mime: str = "application/octet-stream",
    ext: str = "",
    source: str = "",
    prompt: str = "",
    alt: str = "",
    tool_call_id: str = "",
    session_key: str = "",
) -> dict[str, str]:
    suffix = ext or _EXT_BY_MIME.get((mime or "").lower(), "")
    prefix = "img" if kind == "image" else kind
    resource_id = f"{prefix}_{uuid.uuid4().hex}{suffix}"
    filename = resource_id
    path = _kind_dir(kind) / filename
    path.write_bytes(data)

    ref = _build_ref(
        resource_id=resource_id,
        kind=kind,
        mime=mime or "application/octet-stream",
        filename=filename,
        source=source,
        prompt=prompt,
        alt=alt,
        tool_call_id=tool_call_id,
        session_key=session_key,
    )
    index = _read_index()
    index[resource_id] = {
        **ref,
        "path": str(path),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "size": len(data),
    }
    _write_index(index)
    return ref


def save_image_bytes(data: bytes, mime: str = "image/png", **metadata: str) -> dict[str, str]:
    return save_bytes(data, kind="image", mime=mime or "image/png", source="generate_image", **metadata)


def save_image_b64(b64: str, mime: str = "image/png", **metadata: str) -> dict[str, str]:
    raw = base64.b64decode("".join((b64 or "").split()))
    return save_image_bytes(raw, mime, **metadata)


def save_data_url(data_url: str, **metadata: str) -> dict[str, str] | None:
    match = _DATA_URL_RE.match((data_url or "").strip())
    if not match:
        return None
    return save_image_b64(match.group("data"), match.group("mime"), **metadata)


def compress_for_upload(
    path: Path,
    *,
    max_side: int = 1024,
    max_bytes: int = 900_000,
) -> tuple[bytes, str, str]:
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


def get_resource(resource_ref_or_id: str) -> dict[str, Any] | None:
    resource_id = _normalize_resource_id(resource_ref_or_id)
    if not resource_id:
        return None
    item = _read_index().get(resource_id)
    if isinstance(item, dict):
        return item

    for kind, folder in _KIND_DIR.items():
        path = resources_dir() / folder / resource_id
        if path.is_file():
            mime = "image/png" if kind == "image" else "application/octet-stream"
            return {**_build_ref(resource_id=resource_id, kind=kind, mime=mime, filename=resource_id), "path": str(path)}
    return None


def resolve_resource_path(resource_ref_or_id: str) -> Path | None:
    resource_id = _normalize_resource_id(resource_ref_or_id)
    if not resource_id:
        return None
    item = get_resource(resource_id)
    if item and isinstance(item.get("path"), str):
        path = Path(item["path"])
        if path.is_file():
            return path

    return None


def refs_from_images_field(images: Any, *, alt: str = "", prompt: str = "") -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for item in images or []:
        if isinstance(item, dict) and isinstance(item.get("b64_json"), str):
            ref = save_image_b64(item["b64_json"], item.get("mime") or "image/png", alt=alt, prompt=prompt)
        else:
            url = _url_from_image_item(item)
            if not isinstance(url, str) or not url:
                continue
            if url.startswith("data:"):
                ref = save_data_url(url, alt=alt, prompt=prompt)
                if ref is None:
                    continue
            elif url.startswith("http://") or url.startswith("https://"):
                ref = {
                    "id": "",
                    "ref": url,
                    "kind": "image",
                    "url": url,
                    "displayUrl": url,
                    "downloadUrl": url,
                    "mime": "image/*",
                }
                if alt:
                    ref["alt"] = alt
                if prompt:
                    ref["prompt"] = prompt
            else:
                continue
        refs.append(ref)
    return refs


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
