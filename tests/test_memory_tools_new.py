from __future__ import annotations

import asyncio
import json
from pathlib import Path

from auraeve.agent.tools.memory_get import MemoryGetTool
from auraeve.agent.tools.memory_status import MemoryStatusTool
from auraeve.memory_lifecycle import MemoryLifecycleService


class _FakeManager:
    def __init__(self, workspace: Path):
        self.workspace = workspace

    async def read_file(self, *, rel_path: str, from_line: int | None = None, lines: int | None = None):
        p = self.workspace / rel_path
        text = p.read_text(encoding="utf-8")
        if from_line is None and lines is None:
            return {"path": rel_path, "text": text}
        split = text.split("\n")
        start = max(1, int(from_line or 1))
        count = max(1, int(lines or len(split)))
        return {"path": rel_path, "text": "\n".join(split[start - 1 : start - 1 + count])}

    def status(self):
        return {"backend": "builtin", "files": 2, "chunks": 10, "search_mode": "hybrid"}


def test_memory_get_tool_supports_line_range(tmp_path: Path) -> None:
    workspace = tmp_path
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "2026-03-15.md").write_text("a\nb\nc\nd\n", encoding="utf-8")
    tool = MemoryGetTool(_FakeManager(workspace))

    out = asyncio.run(tool.execute(path="memory/2026-03-15.md", lines=2, from_=2))
    parsed = json.loads(out)
    assert parsed["path"] == "memory/2026-03-15.md"
    assert parsed["text"] == "b\nc"


def test_memory_status_tool_returns_json() -> None:
    tool = MemoryStatusTool(_FakeManager(Path(".")))
    out = asyncio.run(tool.execute())
    parsed = json.loads(out)
    assert parsed["backend"] == "builtin"
    assert parsed["files"] == 2
    assert parsed["chunks"] == 10


def test_memory_lifecycle_patch_operations() -> None:
    svc = MemoryLifecycleService(
        workspace=Path("."),
        provider=None,  # type: ignore[arg-type]
        model="test-model",
    )
    current = "# MEMORY\n\n## Facts\n- [name] old\n- [city] shanghai\n"
    updated = svc._apply_patch_operations(
        current,
        [
            {"op": "update", "key": "name", "content": "new"},
            {"op": "remove", "key": "city"},
            {"op": "add", "key": "lang", "content": "zh"},
        ],
    )
    assert updated is not None
    assert "- [name] new" in updated
    assert "- [lang] zh" in updated
    assert "city" not in updated

