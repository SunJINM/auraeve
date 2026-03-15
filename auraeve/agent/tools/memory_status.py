from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from auraeve.agent.tools.base import Tool

if TYPE_CHECKING:
    from auraeve.memory.manager import MemoryManager


class MemoryStatusTool(Tool):
    """Expose memory backend/index health for debugging and observability."""

    def __init__(self, manager: "MemoryManager") -> None:
        self._manager = manager

    @property
    def name(self) -> str:
        return "memory_status"

    @property
    def description(self) -> str:
        return "查看记忆系统状态（索引文件数、分片数、脏文件、降级模式、最近错误）。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        return json.dumps(self._manager.status(), ensure_ascii=False, indent=2)

