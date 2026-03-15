from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from auraeve.agent.tools.base import Tool

if TYPE_CHECKING:
    from auraeve.memory.manager import MemoryManager


class MemoryGetTool(Tool):
    """Read specific memory file snippets after memory_search."""

    def __init__(self, manager: "MemoryManager") -> None:
        self._manager = manager

    @property
    def name(self) -> str:
        return "memory_get"

    @property
    def description(self) -> str:
        return (
            "按路径读取记忆文件内容（支持 from/lines 行范围）。"
            "允许读取 MEMORY.md、memory.md、memory/*.md，以及 sessions/*.md（虚拟会话文档）。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "记忆文件路径（相对 workspace）"},
                "from": {"type": "integer", "minimum": 1, "description": "起始行（1-based）"},
                "lines": {"type": "integer", "minimum": 1, "description": "读取行数"},
            },
            "required": ["path"],
        }

    async def execute(self, path: str, from_: int | None = None, lines: int | None = None, **kwargs: Any) -> str:
        from_line = from_ if from_ is not None else kwargs.get("from")
        try:
            result = await self._manager.read_file(
                rel_path=path,
                from_line=from_line,
                lines=lines,
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            return json.dumps(
                {"path": path, "text": "", "disabled": True, "error": str(exc)},
                ensure_ascii=False,
            )
