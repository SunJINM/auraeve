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
    from auraeve.agent.engines.vector.store import Embedder, VectorMemoryStore


class MemorySearchTool(Tool):
    """
    语义搜索记忆库（MEMORY.md + memory/*.md）。

    工具描述刻意写得具有指令性（"必须先调用"），对应 openclaw 的
    "Mandatory recall step" 设计——引导模型在回答历史相关问题前主动搜索。
    """

    def __init__(
        self,
        store: "VectorMemoryStore",
        embedder: "Embedder",
        search_limit: int = 8,
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
        mmr_lambda: float = 0.7,
        half_life_days: float = 30.0,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._search_limit = search_limit
        self._vector_weight = vector_weight
        self._text_weight = text_weight
        self._mmr_lambda = mmr_lambda
        self._half_life_days = half_life_days

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
        max_results: int = 8,
        min_score: float = 0.05,
        **kwargs: Any,
    ) -> str:
        try:
            query_vec = await self._embedder.embed(query)
        except Exception as e:
            return json.dumps(
                {"disabled": True, "reason": f"嵌入生成失败: {e}"},
                ensure_ascii=False,
            )

        try:
            results = self._store.hybrid_search(
                query=query,
                query_vec=query_vec,
                model=self._embedder.model,
                limit=min(max_results, 20),
                vector_weight=self._vector_weight,
                text_weight=self._text_weight,
                half_life_days=self._half_life_days,
                mmr_lambda=self._mmr_lambda,
            )
        except Exception as e:
            return json.dumps(
                {"disabled": True, "reason": f"向量检索失败: {e}"},
                ensure_ascii=False,
            )

        # 过滤低相关性结果
        results = [r for r in results if r.score >= min_score]

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

        return json.dumps(
            {"results": items, "total": len(items)},
            ensure_ascii=False,
            indent=2,
        )
