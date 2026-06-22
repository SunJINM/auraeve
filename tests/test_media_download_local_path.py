import asyncio
import base64
import io
import random
from pathlib import Path

from PIL import Image

from auraeve.agent.media import download_and_extract, extract_file_content


def test_download_and_extract_supports_local_file_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "sample.txt"
    src.write_text("hello local file", encoding="utf-8")

    result = asyncio.run(download_and_extract(str(src), workspace, original_filename=src.name))
    assert result.filename == "sample.txt"
    assert "hello local file" in result.text


def test_extract_file_content_compresses_large_images_for_llm() -> None:
    rng = random.Random(42)
    pixels = bytes(rng.randrange(256) for _ in range(1400 * 1400 * 3))
    buf = io.BytesIO()
    image = Image.frombytes("RGB", (1400, 1400), pixels)
    image.save(buf, format="PNG")
    raw = buf.getvalue()
    assert len(raw) > 900_000

    result = asyncio.run(extract_file_content(raw, "image/png", "large.png"))

    assert result.images
    encoded = base64.b64decode(result.images[0].data)
    assert result.images[0].mime_type in {"image/png", "image/jpeg"}
    assert len(encoded) <= 900_000
