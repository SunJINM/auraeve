"""
媒体文件处理模块（对标 openclaw media/input-files.ts + pdf-extract.ts + mime.ts）

职责：
1. MIME 嗅探（魔数优先，扩展名/Content-Type 兜底）
2. 从 URL 下载文件到本地临时目录（TTL 自动清理）
3. 按类型提取内容：
   - image/*       → base64，供视觉模型 image_url block
   - application/pdf → pdfminer 提文本；文本稀少时 pdf2image 渲染为 PNG 图片（fallback）
   - text/*         → 解码为文本，截断至 MAX_TEXT_CHARS
   - 其他           → 仅返回文件名+大小描述
"""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

# ── 对标 openclaw 的限制常量 ──────────────────────────────────────────────────
MAX_FILE_BYTES = 5 * 1024 * 1024    # 5MB
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB
MAX_TEXT_CHARS = 200_000
PDF_MAX_PAGES = 4
PDF_MIN_TEXT_CHARS = 200            # 低于此字符数则 fallback 到图片渲染
MEDIA_TTL_SECONDS = 120             # 2 分钟，对标 openclaw DEFAULT_TTL_MS
DOWNLOAD_TIMEOUT_S = 15

# 对标 openclaw mime.ts 的 EXT_BY_MIME
_EXT_BY_MIME: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/x-m4a": ".m4a",
    "audio/mp4": ".m4a",
    "video/mp4": ".mp4",
    "application/pdf": ".pdf",
    "application/json": ".json",
    "application/msword": ".doc",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/html": ".html",
    "text/csv": ".csv",
}
_MIME_BY_EXT: dict[str, str] = {v: k for k, v in _EXT_BY_MIME.items()}
_MIME_BY_EXT.update({
    ".jpeg": "image/jpeg",
    ".js": "text/javascript",
    ".py": "text/x-python",
    ".ts": "text/typescript",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".xml": "application/xml",
    ".sh": "text/x-shellscript",
})

# 支持的文件 MIME 集合（对标 openclaw DEFAULT_INPUT_FILE_MIMES）
SUPPORTED_FILE_MIMES: set[str] = {
    "text/plain", "text/markdown", "text/html", "text/csv",
    "application/json", "application/pdf",
    "text/x-python", "text/javascript", "text/typescript",
    "text/yaml", "application/xml", "text/x-shellscript",
}
SUPPORTED_IMAGE_MIMES: set[str] = {
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/heic", "image/heif",
}


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class ExtractedImage:
    """提取出的图片内容（对标 openclaw PdfExtractedImage）。"""
    data: str       # base64
    mime_type: str  # e.g. "image/png"


@dataclass
class FileExtractResult:
    """文件内容提取结果（对标 openclaw InputFileExtractResult）。"""
    filename: str
    text: str = ""
    images: list[ExtractedImage] = field(default_factory=list)
    description: str = ""   # 无法提取时的纯描述（文件名+大小）


# ── MIME 嗅探 ─────────────────────────────────────────────────────────────────

def _sniff_mime_from_bytes(data: bytes) -> str | None:
    """通过魔数检测真实 MIME 类型（对标 openclaw file-type 库）。"""
    try:
        import magic  # python-magic
        return magic.from_buffer(data[:4096], mime=True) or None
    except ImportError:
        pass
    # 内建魔数表（兜底，无需 libmagic）
    if data[:4] == b"%PDF":
        return "application/pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:2] in (b"\xff\xd8",):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:2] in (b"PK",) and data[2:4] in (b"\x03\x04", b"\x05\x06", b"\x07\x08"):
        # ZIP 容器，可能是 DOCX/XLSX
        return "application/zip"
    return None


def detect_mime(
    data: bytes | None = None,
    header_mime: str | None = None,
    file_path: str | None = None,
) -> str:
    """
    MIME 检测，优先级（对标 openclaw detectMimeImpl）：
    1. 魔数嗅探（最高，非泛型）
    2. 文件扩展名映射
    3. Content-Type 头（非泛型）
    4. 魔数嗅探（泛型容器）
    5. Content-Type 头（泛型）
    6. application/octet-stream 兜底
    """
    ext_mime: str | None = None
    if file_path:
        ext = Path(file_path).suffix.lower()
        ext_mime = _MIME_BY_EXT.get(ext) or mimetypes.guess_type(file_path)[0]

    sniffed: str | None = _sniff_mime_from_bytes(data) if data else None

    # 非泛型 sniffed 优先（zip 是泛型）
    _generic = {"application/octet-stream", "application/zip"}
    if sniffed and sniffed not in _generic:
        # 但不能让 zip 覆盖更精确的扩展名映射（xlsx vs zip）
        return sniffed
    if ext_mime:
        return ext_mime
    if header_mime:
        h = header_mime.split(";")[0].strip().lower()
        if h not in _generic:
            return h
    if sniffed:
        return sniffed
    if header_mime:
        return header_mime.split(";")[0].strip().lower()
    return "application/octet-stream"


# ── 媒体目录管理 ──────────────────────────────────────────────────────────────

def get_media_dir(workspace: Path) -> Path:
    """返回媒体存储目录（workspace/media/inbox/）。"""
    return workspace / "media" / "inbox"


def ensure_media_dir(workspace: Path) -> Path:
    d = get_media_dir(workspace)
    d.mkdir(parents=True, exist_ok=True)
    return d


def clean_old_media(workspace: Path, ttl_seconds: float = MEDIA_TTL_SECONDS) -> None:
    """清理超过 TTL 的临时媒体文件（对标 openclaw cleanOldMedia）。"""
    d = get_media_dir(workspace)
    if not d.exists():
        return
    now = time.time()
    for f in d.iterdir():
        if f.is_file() and (now - f.stat().st_mtime) > ttl_seconds:
            try:
                f.unlink()
            except OSError:
                pass


def save_media_bytes(
    data: bytes,
    workspace: Path,
    content_type: str | None = None,
    original_filename: str | None = None,
) -> Path:
    """
    将字节写入媒体目录，文件名格式：{sanitized}---{uuid}{ext}
    对标 openclaw saveMediaBuffer。
    """
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"文件过大：{len(data)} 字节（限制 {MAX_FILE_BYTES} 字节）")

    mime = detect_mime(data, content_type, original_filename)
    ext = _EXT_BY_MIME.get(mime, "")
    if not ext and original_filename:
        ext = Path(original_filename).suffix.lower()

    uid = str(uuid.uuid4())
    if original_filename:
        base = Path(original_filename).stem[:60]
        # 移除不安全字符
        import re
        base = re.sub(r"[^\w\-.]", "_", base).strip("_")
        filename = f"{base}---{uid}{ext}" if base else f"{uid}{ext}"
    else:
        filename = f"{uid}{ext}"

    dest = ensure_media_dir(workspace) / filename
    dest.write_bytes(data)
    return dest


# ── 下载 ──────────────────────────────────────────────────────────────────────

async def download_url(
    url: str,
    max_bytes: int = MAX_FILE_BYTES,
    timeout_s: float = DOWNLOAD_TIMEOUT_S,
    headers: dict[str, str] | None = None,
) -> tuple[bytes, str | None]:
    """
    下载 URL 内容，返回 (bytes, content_type)。
    对标 openclaw fetchWithGuard（简化版，无 SSRF 防护）。
    """
    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
        r = await client.get(url, headers=headers or {})
        r.raise_for_status()
        content_type = r.headers.get("content-type")
        data = r.content
        if len(data) > max_bytes:
            raise ValueError(f"文件过大：{len(data)} 字节（限制 {max_bytes} 字节）")
        return data, content_type


# ── PDF 提取（对标 openclaw extractPdfContent）─────────────────────────────────

def _extract_pdf_text(data: bytes, max_pages: int = PDF_MAX_PAGES) -> str:
    """用 pdfminer.six 提取 PDF 文字。"""
    try:
        from pdfminer.high_level import extract_text_to_fp
        from pdfminer.layout import LAParams
        import io
        out = io.StringIO()
        extract_text_to_fp(
            io.BytesIO(data), out,
            laparams=LAParams(),
            page_numbers=list(range(max_pages)),
        )
        return out.getvalue().strip()
    except ImportError:
        # 尝试 pdfplumber（项目已有依赖）
        try:
            import pdfplumber, io
            parts = []
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for i, page in enumerate(pdf.pages[:max_pages]):
                    t = page.extract_text() or ""
                    if t.strip():
                        parts.append(t.strip())
            return "\n\n".join(parts)
        except ImportError:
            return ""


def _render_pdf_pages_as_images(data: bytes, max_pages: int = PDF_MAX_PAGES) -> list[ExtractedImage]:
    """
    将 PDF 页面渲染为 PNG（对标 openclaw 的 canvas 渲染 fallback）。
    需要 pdf2image + poppler。
    """
    try:
        from pdf2image import convert_from_bytes
    except ImportError:
        logger.warning("pdf2image 未安装，无法渲染 PDF 图片。pip install pdf2image")
        return []
    try:
        import io
        images = convert_from_bytes(data, first_page=1, last_page=max_pages, dpi=120)
        result = []
        for img in images:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            result.append(ExtractedImage(data=b64, mime_type="image/png"))
        return result
    except Exception as e:
        logger.warning(f"PDF 渲染失败：{e}")
        return []


async def extract_pdf_content(data: bytes) -> FileExtractResult:
    """
    PDF 内容提取（对标 openclaw extractPdfContent）：
    - 先提取文字；文字 >= PDF_MIN_TEXT_CHARS → 返回文本
    - 文字稀少（扫描件）→ fallback 渲染为 PNG 图片
    """
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, _extract_pdf_text, data, PDF_MAX_PAGES)

    if len(text.strip()) >= PDF_MIN_TEXT_CHARS:
        clamped = text[:MAX_TEXT_CHARS]
        return FileExtractResult(filename="", text=clamped)

    # 文本稀少 → 渲染图片
    logger.debug(f"PDF 文本稀少（{len(text.strip())} 字），尝试渲染为图片")
    images = await loop.run_in_executor(None, _render_pdf_pages_as_images, data, PDF_MAX_PAGES)
    return FileExtractResult(filename="", text=text, images=images)


# ── 文件内容提取（核心入口）──────────────────────────────────────────────────

async def extract_file_content(
    data: bytes,
    mime_type: str,
    filename: str = "file",
) -> FileExtractResult:
    """
    按 MIME 类型提取文件内容（对标 openclaw extractFileContentFromSource）。

    返回 FileExtractResult：
    - text   → 供注入 LLM 文本上下文
    - images → 供 image_url content block
    - description → 无法提取时的占位描述
    """
    size_kb = len(data) / 1024

    # 图片
    if mime_type.startswith("image/"):
        if len(data) > MAX_IMAGE_BYTES:
            return FileExtractResult(
                filename=filename,
                description=f"[图片: {filename}, {size_kb:.0f}KB，超过大小限制]",
            )
        b64 = base64.b64encode(data).decode()
        return FileExtractResult(
            filename=filename,
            images=[ExtractedImage(data=b64, mime_type=mime_type)],
        )

    # PDF
    if mime_type == "application/pdf":
        result = await extract_pdf_content(data)
        result.filename = filename
        return result

    # 文本类（包括 text/* 和 JSON/XML 等）
    _text_mimes = {
        "application/json", "application/xml", "application/x-yaml",
    }
    if mime_type.startswith("text/") or mime_type in _text_mimes:
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = data.decode("latin-1", errors="replace")
        clamped = text[:MAX_TEXT_CHARS]
        return FileExtractResult(filename=filename, text=clamped)

    # 其他二进制：仅描述
    return FileExtractResult(
        filename=filename,
        description=f"[文件: {filename}, {size_kb:.0f}KB, {mime_type}]",
    )


# ── 完整下载+提取流程 ─────────────────────────────────────────────────────────

async def download_and_extract(
    url: str,
    workspace: Path,
    original_filename: str | None = None,
    headers: dict[str, str] | None = None,
) -> FileExtractResult:
    """
    下载 URL → 保存到 media/inbox/ → 提取内容。
    自动清理超 TTL 旧文件。
    """
    try:
        clean_old_media(workspace)
        source = str(url or "").strip()
        local_path: Path | None = None
        if source.lower().startswith("file://"):
            local_candidate = source[7:]
            if local_candidate.startswith("/") and len(local_candidate) > 3 and local_candidate[2] == ":":
                # Windows file:///C:/... 兼容
                local_candidate = local_candidate[1:]
            local_path = Path(local_candidate)
        elif source and not source.lower().startswith(("http://", "https://")):
            local_path = Path(source)

        if local_path is not None and local_path.exists() and local_path.is_file():
            data = local_path.read_bytes()
            if len(data) > MAX_FILE_BYTES:
                raise ValueError(f"文件过大：{len(data)} 字节（限制 {MAX_FILE_BYTES} 字节）")
            content_type = None
            fname = original_filename or local_path.name or "file"
        else:
            data, content_type = await download_url(source, headers=headers)
            fname = original_filename or "file"

        mime = detect_mime(data, content_type, original_filename)
        # 保存到本地（供 Agent 后续用 read_file 工具访问）
        local_path = save_media_bytes(data, workspace, content_type, fname)
        logger.debug(f"媒体文件已下载：{local_path.name} ({mime}, {len(data)/1024:.0f}KB)")
        result = await extract_file_content(data, mime, fname)
        result.filename = fname
        return result
    except Exception as e:
        logger.warning(f"文件下载/提取失败（{url}）：{e}")
        return FileExtractResult(
            filename=original_filename or "file",
            description=f"[文件下载失败: {original_filename or url}, 原因: {e}]",
        )
