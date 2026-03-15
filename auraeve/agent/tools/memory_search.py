"""
memory_search 工具：显式语义搜索记忆库。

对标 openclaw 的 memory_search 工具设计：
- 不自动注入系统提示词，而是让模型在需要时主动调用
- 返回 path + 行号 + 相关片段，便于精确引用
- 工具描述明确告知模型"何时必须调用"
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from auraeve.agent.tools.base import Tool

if TYPE_CHECKING:
    from auraeve.memory.manager import MemoryManager


class MemorySearchTool(Tool):
    """
    语义搜索记忆库（MEMORY.md + memory/*.md）。

    工具描述刻意写得具有指令性（"必须先调用"），对应 openclaw 的
    "Mandatory recall step" 设计——引导模型在回答历史相关问题前主动搜索。
    """

    def __init__(
        self,
        manager: "MemoryManager",
        search_limit: int = 8,
    ) -> None:
        self._manager = manager
        self._search_limit = search_limit

    @property
    def name(self) -> str:
        return "memory_search"

    @property
    def description(self) -> str:
        return (
            "必须先调用的记忆检索步骤：在回答以下类型问题前，语义搜索记忆库（MEMORY.md + memory/*.md）：\n"
            "- 过去的工作、任务进展、已做的决策\n"
            "- 用户历史提到的偏好、人名、日期、约定\n"
            "- 之前对话的上下文与待办事项\n"
            "返回相关片段（含来源路径和行号）。若返回 disabled=true，记忆检索不可用。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询，用自然语言描述你想找什么",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最多返回条数（默认 8，最大 20）",
                    "minimum": 1,
                    "maximum": 20,
                },
                "min_score": {
                    "type": "number",
                    "description": "最低相关性分数（0~1，默认 0.05）",
                    "minimum": 0,
                    "maximum": 1,
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        max_results: int | None = None,
        min_score: float = 0.05,
        **kwargs: Any,
    ) -> str:
        resolved_limit = max_results if max_results is not None else self._search_limit
        try:
            results = await self._manager.search(
                query=query,
                max_results=min(resolved_limit, 20),
                min_score=min_score,
            )
        except Exception as e:
            return json.dumps(
                {"disabled": True, "reason": f"记忆检索失败: {e}"},
                ensure_ascii=False,
            )

        if not results:
            return json.dumps(
                {"results": [], "message": "未找到相关记忆。可尝试更换关键词或扩大 max_results。"},
                ensure_ascii=False,
            )

        items = []
        for r in results:
            item: dict[str, Any] = {
                "path": r.path,
                "snippet": r.snippet,
                "score": round(r.score, 3),
            }
            start = getattr(r, "start_line", None)
            end = getattr(r, "end_line", None)
            if start and end:
                item["lines"] = f"{start}-{end}"
            items.append(item)

        status = self._manager.status()
        return json.dumps(
            {
                "results": items,
                "total": len(items),
                "mode": status.get("search_mode", "hybrid"),
                "warning": (
                    "embedding 不可用，当前使用关键词降级检索"
                    if status.get("search_mode") == "fts-only"
                    else ""
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
