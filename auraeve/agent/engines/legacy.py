"""LegacyContextEngine：包装现有 ContextBuilder，不做记忆检索和压缩。"""

from __future__ import annotations

from pathlib import Path

from auraeve.agent.engines.base import AssembleResult, ContextEngine


class LegacyContextEngine(ContextEngine):
    """直接调用 ContextBuilder，不做记忆检索和压缩。"""

    def __init__(
        self,
        workspace: Path,
        memory_window: int = 50,
        execution_workspace: str | None = None,
    ) -> None:
        from auraeve.agent.context import ContextBuilder
        self._builder = ContextBuilder(workspace, execution_workspace=execution_workspace)
        self._memory_window = memory_window

    async def assemble(
        self,
        session_id: str,
        messages: list[dict],
        current_query: str,
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
        assembled = self._builder.build_messages(
            history=messages[-self._memory_window:],
            current_message=current_query,
            media=media,
            attachments=attachments,
            channel=channel,
            chat_id=chat_id,
            available_tools=available_tools,
            prompt_mode=prompt_mode,
            prepend_context=prepend_context,
            append_context=append_context,
        )
        estimated = sum(len(str(m.get("content", ""))) // 4 + 128 for m in assembled)
        return AssembleResult(messages=assembled, estimated_tokens=estimated)
