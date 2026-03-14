"""
VectorContextEngine：向量记忆检索 + 自动上下文压缩。

架构变更（对标 openclaw memory_search 工具设计）：
- 记忆检索不再自动注入系统提示词
- 改由 memory_search 工具（MemorySearchTool）显式调用
- assemble() 只构建系统提示词 + 历史 + 用户消息，不注入记忆片段
- after_turn() 继续增量重索引记忆文件，保持向量库更新
"""

from __future__ import annotations

import hashlib
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

_context_builder_cls = None


def _get_context_builder():
    global _context_builder_cls
    if _context_builder_cls is None:
        from auraeve.agent.context import ContextBuilder
        _context_builder_cls = ContextBuilder
    return _context_builder_cls


_EVERGREEN_FILES = {"MEMORY.MD", "AGENTS.MD", "SOUL.MD", "USER.MD", "TOOLS.MD", "IDENTITY.MD"}


class VectorContextEngine(ContextEngine):
    """
    完整上下文引擎：
    1. 上下文超限时自动压缩（LLM 摘要 + 标识符保全）
    2. 每轮结束后增量重索引记忆文件（供 memory_search 工具使用）
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
        self._context_builder = _get_context_builder()(
            workspace,
            execution_workspace=execution_workspace,
        )

    async def bootstrap(self) -> None:
        """启动时全量索引记忆文件。"""
        indexed = await self._reindex_memory_files()
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
        """每轮结束后增量重索引记忆文件。"""
        indexed = await self._reindex_memory_files()
        if indexed > 0:
            logger.debug(f"记忆文件重索引：{indexed} 个文件已更新")

    async def _reindex_memory_files(self) -> int:
        """扫描 workspace/memory/ 下所有 .md 文件，增量重索引。"""
        memory_dir = self.workspace / "memory"
        if not memory_dir.exists():
            return 0

        total = 0
        for file_path in sorted(memory_dir.glob("*.md")):
            basename = file_path.name.upper()
            source = "memory" if basename in _EVERGREEN_FILES else "daily"

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                file_hash = hashlib.sha256(content.encode()).hexdigest()
            except Exception:
                continue

            cached_hash = self.store.get_file_hash(str(file_path))
            if cached_hash == file_hash:
                continue

            try:
                count = await self.store.index_file(file_path, source, self.embedder)
                if count > 0:
                    logger.debug(f"  索引 {file_path.name}：{count} 个片段")
                    total += 1
            except Exception as e:
                logger.warning(f"  索引 {file_path.name} 失败：{e}")

        return total
