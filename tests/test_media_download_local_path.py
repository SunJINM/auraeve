import asyncio
from pathlib import Path

from auraeve.agent.media import download_and_extract


def test_download_and_extract_supports_local_file_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "sample.txt"
    src.write_text("hello local file", encoding="utf-8")

    result = asyncio.run(download_and_extract(str(src), workspace, original_filename=src.name))
    assert result.filename == "sample.txt"
    assert "hello local file" in result.text
