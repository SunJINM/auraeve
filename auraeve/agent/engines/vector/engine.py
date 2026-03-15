"""
VectorContextEngine：向量记忆检索 + 自动上下文压缩。

架构变更（对标 openclaw memory_search 工具设计）：
- 记忆检索不再自动注入系统提示词
- 改由 memory_search 工具（MemorySearchTool）显式调用
- assemble() 只构建系统提示词 + 历史 + 用户消息，不注入记忆片段
- 索引同步由 MemoryManager 管理（增量 + 周期扫描 + 可选 sessions 源）
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from auraeve.providers.base import LLMProvider

from auraeve.agent.engines.base import AssembleResult, ContextEngine
from auraeve.agent.engines.vector.compaction import (
    compact_messages,
    estimate_tokens,
    should_compact,
)
from auraeve.agent.engines.vector.store import Embedder, VectorMemoryStore
from auraeve.memory import MemoryManager

_context_builder_cls = None


def _get_context_builder():
    global _context_builder_cls
    if _context_builder_cls is None:
        from auraeve.agent.context import ContextBuilder
        _context_builder_cls = ContextBuilder
    return _context_builder_cls


class VectorContextEngine(ContextEngine):
    """
    完整上下文引擎：
    1. 上下文超限时自动压缩（LLM 摘要 + 标识符保全）
    2. 每轮结束后触发 MemoryManager 增量同步（供 memory_search 工具使用）
    3. 记忆检索已移交给 MemorySearchTool（显式工具，按需调用）
    """

    def __init__(
        self,
        workspace: Path,
        db_path: Path,
        embedder: Embedder,
        provider: "LLMProvider",
        token_budget: int = 120_000,
        compact_threshold: float = 0.85,
        search_limit: int = 8,
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
        mmr_lambda: float = 0.7,
        half_life_days: float = 30.0,
        sessions_dir: Path | None = None,
        include_sessions: bool = False,
        sessions_max_messages: int = 400,
        execution_workspace: str | None = None,
    ) -> None:
        self.workspace = workspace
        self.embedder = embedder
        self.provider = provider
        self.token_budget = token_budget
        self.compact_threshold = compact_threshold
        self.search_limit = search_limit
        self.vector_weight = vector_weight
        self.text_weight = text_weight
        self.mmr_lambda = mmr_lambda
        self.half_life_days = half_life_days

        self.store = VectorMemoryStore(db_path)
        self.memory_manager = MemoryManager(
            workspace=workspace,
            store=self.store,
            embedder=self.embedder,
            search_limit=self.search_limit,
            vector_weight=self.vector_weight,
            text_weight=self.text_weight,
            mmr_lambda=self.mmr_lambda,
            half_life_days=self.half_life_days,
            sessions_dir=sessions_dir,
            include_sessions=include_sessions,
            sessions_max_messages=sessions_max_messages,
        )
        self._context_builder = _get_context_builder()(
            workspace,
            execution_workspace=execution_workspace,
        )

    async def bootstrap(self) -> None:
        """启动时全量索引记忆文件并启动后台增量扫描。"""
        indexed = await self.memory_manager.bootstrap()
        logger.info(f"向量记忆引擎初始化：已索引 {indexed} 个记忆文件")

    async def assemble(
        self,
        session_id: str,
        messages: list[dict],
        current_query: str,
        identity_context: str | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        media: list[str] | None = None,
        attachments: list | None = None,
        token_budget: int | None = None,
        available_tools: set[str] | None = None,
        prompt_mode: str = "full",
        prepend_context: str | None = None,
        append_context: str | None = None,
    ) -> AssembleResult:
        budget = token_budget or self.token_budget

        system_prompt = self._context_builder.build_system_prompt(
            channel=channel,
            chat_id=chat_id,
            available_tools=available_tools,
            prompt_mode=prompt_mode,
            prepend_context=prepend_context,
            append_context=append_context,
        )
        user_content = self._context_builder._build_user_content(current_query, media, attachments)

        assembled = (
            [{"role": "system", "content": system_prompt}]
            + list(messages)
            + [{"role": "user", "content": user_content}]
        )

        if should_compact(assembled, budget, self.compact_threshold):
            logger.info(
                f"上下文接近 token 上限（估算 {estimate_tokens(assembled)} / {budget}），"
                f"触发自动压缩…"
            )
            result = await compact_messages(
                messages=list(messages),
                budget=budget,
                provider=self.provider,
            )
            if result.compacted and result.compacted_messages is not None:
                assembled = (
                    [{"role": "system", "content": system_prompt}]
                    + result.compacted_messages
                    + [{"role": "user", "content": user_content}]
                )
                return AssembleResult(
                    messages=assembled,
                    estimated_tokens=estimate_tokens(assembled),
                    compacted_messages=result.compacted_messages,
                )

        return AssembleResult(
            messages=assembled,
            estimated_tokens=estimate_tokens(assembled),
        )

    async def after_turn(self, session_id: str, messages: list[dict]) -> None:
        """每轮结束后执行事件驱动增量同步。"""
        indexed = await self.memory_manager.sync(reason="turn", force=False)
        if indexed > 0:
            logger.debug(f"记忆文件重索引：{indexed} 个文件已更新")
