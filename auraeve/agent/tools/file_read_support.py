from __future__ import annotations

import base64
import io
import json
import mimetypes
from pathlib import Path
from typing import Any

from auraeve.agent.tools.base import ToolExecutionResult


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".amr", ".silk"}
FILE_UNCHANGED_STUB = (
    "File unchanged since last read. The content from the earlier Read tool_result "
    "in this conversation is still current - refer to that instead of re-reading."
)
MAX_LINES_TO_READ = 2000
MAX_TEXT_READ_TOKENS = 10000
MAX_PDF_PAGES_WITHOUT_PAGES = 10
MAX_PDF_PAGES_PER_REQUEST = 20
MAX_IMAGE_EDGE = 1568
MAX_IMAGE_BYTES = 1_200_000


def estimate_token_count(text: str) -> int:
    return max(1, len(text) // 4)


def format_text_with_line_numbers(text: str, offset: int | None, limit: int | None) -> str:
    lines = text.splitlines()
    start = max(0, int(offset or 0))
    count = int(limit) if limit is not None else max(0, len(lines) - start)
    selected = lines[start : start + count]
    return "\n".join(f"{start + idx + 1}\t{line}" for idx, line in enumerate(selected))


def read_text_file(path: Path, offset: int | None = None, limit: int | None = None) -> ToolExecutionResult:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    start = max(0, int(offset or 0))
    count = int(limit) if limit is not None else max(0, len(lines) - start)
    selected = lines[start : start + count]
    selected_text = "\n".join(selected)
    token_count = estimate_token_count(selected_text)
    if token_count > MAX_TEXT_READ_TOKENS:
        return ToolExecutionResult(
            content=(
                "Error: File content "
                f"({token_count} tokens) exceeds maximum allowed tokens "
                f"({MAX_TEXT_READ_TOKENS}). Use offset and limit parameters to read "
                "specific portions of the file, or search for specific content instead "
                "of reading the whole file."
            ),
            data={
                "type": "error",
                "filePath": str(path),
                "offset": offset,
                "limit": limit,
                "estimatedTokens": token_count,
                "maxTokens": MAX_TEXT_READ_TOKENS,
            },
        )
    rendered = format_text_with_line_numbers(raw, offset, limit)
    return ToolExecutionResult(
        content=rendered,
        data={"type": "text", "filePath": str(path), "offset": offset, "limit": limit},
    )


def parse_pdf_pages(pages: str | None, total_pages: int) -> list[int]:
    if total_pages <= 0:
        return []
    if not pages or not str(pages).strip():
        return list(range(total_pages))

    page_numbers: set[int] = set()
    for raw_part in str(pages).split(","):
        part = raw_part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            if start_text.strip():
                start = int(start_text.strip())
            else:
                start = 1
            if end_text.strip():
                end = int(end_text.strip())
            else:
                end = total_pages
            if start < 1 or end < start:
                raise ValueError(f"Invalid PDF page range: {pages}")
            for page in range(start, min(end, total_pages) + 1):
                page_numbers.add(page - 1)
        else:
            page = int(part)
            if page < 1 or page > total_pages:
                raise ValueError(f"Invalid PDF page number: {page}")
            page_numbers.add(page - 1)

    ordered = sorted(page_numbers)
    if len(ordered) > MAX_PDF_PAGES_PER_REQUEST:
        raise ValueError(
            f"Read can load at most {MAX_PDF_PAGES_PER_REQUEST} PDF pages per request"
        )
    return ordered


def read_notebook_file(path: str) -> ToolExecutionResult:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    cells_payload: list[dict[str, Any]] = []
    rendered_cells: list[str] = []
    for index, cell in enumerate(raw.get("cells", []), start=1):
        source = _normalize_notebook_source(cell.get("source", []))
        outputs = _extract_notebook_outputs(cell.get("outputs", []))
        payload = {
            "cellNumber": index,
            "cellType": cell.get("cell_type", "unknown"),
            "source": source,
            "outputs": outputs,
        }
        cells_payload.append(payload)
        rendered = f"[cell {index} {payload['cellType']}]\n{source}"
        if outputs:
            rendered += "\n\n[outputs]\n" + "\n".join(outputs)
        rendered_cells.append(rendered)

    return ToolExecutionResult(
        content="\n\n".join(rendered_cells),
        data={"type": "notebook", "filePath": path, "cells": cells_payload},
    )


async def read_image_file(path: str) -> ToolExecutionResult:
    mime = mimetypes.guess_type(path)[0] or _mime_from_suffix(Path(path).suffix.lower())
    data_url = encode_image_as_data_url(Path(path))
    return ToolExecutionResult(
        content=f"Image read successfully: {path}",
        extra_messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Image file: {path}"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        data={"type": "image", "filePath": path, "mimeType": mime},
    )


def get_pdf_page_count(path: str) -> int:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        return len(pdf.pages)


async def read_pdf_file(path: str, pages: str | None) -> ToolExecutionResult:
    total_pages = get_pdf_page_count(path)
    if total_pages > MAX_PDF_PAGES_WITHOUT_PAGES and not pages:
        return ToolExecutionResult(
            content=(
                "Error: PDF has more than "
                f"{MAX_PDF_PAGES_WITHOUT_PAGES} pages; provide the pages parameter"
            ),
            data={"type": "error", "filePath": path},
        )

    page_indices = parse_pdf_pages(pages, total_pages)
    extracted_text = _extract_pdf_text(path, page_indices)
    page_label = pages or _pages_to_label(page_indices)
    result_type = "parts" if pages else "pdf"
    if extracted_text.strip():
        return ToolExecutionResult(
            content=f"PDF read successfully: {path} ({page_label})",
            extra_messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": extracted_text,
                        }
                    ],
                }
            ],
            data={
                "type": result_type,
                "filePath": path,
                "pages": page_label,
                "text": extracted_text,
            },
        )

    image_urls = _render_pdf_pages_as_data_urls(path, page_indices)
    blocks: list[dict[str, Any]] = [
        {"type": "text", "text": f"PDF file: {path} ({page_label})"}
    ]
    blocks.extend({"type": "image_url", "image_url": {"url": url}} for url in image_urls)
    return ToolExecutionResult(
        content=f"PDF rendered successfully: {path} ({page_label})",
        extra_messages=[{"role": "user", "content": blocks}] if len(blocks) > 1 else [],
        data={
            "type": result_type,
            "filePath": path,
            "pages": page_label,
            "renderedPages": len(image_urls),
        },
    )


def _normalize_notebook_source(source: Any) -> str:
    if isinstance(source, list):
        return "".join(str(part) for part in source)
    return str(source or "")


def _extract_notebook_outputs(outputs: Any) -> list[str]:
    rendered: list[str] = []
    if not isinstance(outputs, list):
        return rendered
    for output in outputs:
        if not isinstance(output, dict):
            continue
        text_value = output.get("text")
        if isinstance(text_value, list):
            rendered.append("".join(str(part) for part in text_value))
            continue
        if isinstance(text_value, str):
            rendered.append(text_value)
            continue
        data = output.get("data")
        if isinstance(data, dict):
            plain = data.get("text/plain")
            if isinstance(plain, list):
                rendered.append("".join(str(part) for part in plain))
            elif isinstance(plain, str):
                rendered.append(plain)
    return rendered


def _extract_pdf_text(path: str, page_indices: list[int]) -> str:
    try:
        import pdfplumber
    except ImportError:
        return ""

    parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page_index in page_indices:
            if page_index >= len(pdf.pages):
                continue
            text = pdf.pages[page_index].extract_text() or ""
            if text.strip():
                parts.append(f"--- Page {page_index + 1} ---\n{text.strip()}")
    return "\n\n".join(parts)


def _render_pdf_pages_as_data_urls(path: str, page_indices: list[int]) -> list[str]:
    try:
        from pdf2image import convert_from_bytes
    except ImportError:
        return []

    pdf_bytes = Path(path).read_bytes()
    urls: list[str] = []
    for page_index in page_indices:
        try:
            rendered = convert_from_bytes(
                pdf_bytes,
                first_page=page_index + 1,
                last_page=page_index + 1,
                dpi=120,
            )
        except Exception:
            continue
        if not rendered:
            continue
        buf = io.BytesIO()
        rendered[0].save(buf, format="PNG")
        urls.append(f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}")
    return urls


def encode_image_as_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or _mime_from_suffix(path.suffix.lower())
    return _encode_image_for_llm(path, mime)


def _encode_image_for_llm(path: Path, mime: str) -> str:
    original_bytes = path.read_bytes()
    try:
        from PIL import Image
    except ImportError:
        return f"data:{mime};base64,{base64.b64encode(original_bytes).decode('ascii')}"

    try:
        with Image.open(io.BytesIO(original_bytes)) as img:
            img.load()
            resized = img.copy()
            if max(resized.size) > MAX_IMAGE_EDGE:
                resized.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))

            candidate = _encode_pil_image(resized, mime)
            if len(candidate) <= MAX_IMAGE_BYTES:
                return f"data:{mime};base64,{base64.b64encode(candidate).decode('ascii')}"

            for quality in (85, 70, 55, 40):
                downscaled = resized.copy()
                if max(downscaled.size) > 768:
                    downscaled.thumbnail((768, 768))
                candidate = _encode_pil_image(downscaled, "image/jpeg", quality=quality)
                if len(candidate) <= MAX_IMAGE_BYTES:
                    return (
                        "data:image/jpeg;base64,"
                        + base64.b64encode(candidate).decode("ascii")
                    )
    except Exception:
        pass

    return f"data:{mime};base64,{base64.b64encode(original_bytes).decode('ascii')}"


def _encode_pil_image(image: Any, mime: str, quality: int = 85) -> bytes:
    buf = io.BytesIO()
    fmt = "PNG"
    save_kwargs: dict[str, Any] = {}
    if mime == "image/jpeg":
        fmt = "JPEG"
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        save_kwargs["quality"] = quality
        save_kwargs["optimize"] = True
    else:
        save_kwargs["optimize"] = True
    image.save(buf, format=fmt, **save_kwargs)
    return buf.getvalue()


def _mime_from_suffix(suffix: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(suffix, "image/png")


def _pages_to_label(page_indices: list[int]) -> str:
    if not page_indices:
        return ""
    if len(page_indices) == 1:
        return str(page_indices[0] + 1)
    return f"{page_indices[0] + 1}-{page_indices[-1] + 1}"
