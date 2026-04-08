"""PromptAssembler：分段 Prompt 管线 + before_prompt_build hook 接入 + 预算报告。

流程：
  1. 运行 before_prompt_build hook → 获取 prepend/append 上下文
  2. 调用 ContextEngine.assemble()（已支持 prepend/append 参数）
  3. 生成 BudgetReport（用于 debug/审计）
  4. 返回 AssemblerResult
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger

from .segments import BudgetReport, PromptSegment, estimate_tokens

if TYPE_CHECKING:
    from auraeve.agent.engines.base import AssembleResult, ContextEngine
    from auraeve.plugins.hooks import HookRunner


@dataclass
class AssemblerResult:
    """PromptAssembler.assemble() 的返回值。"""
    messages: list[dict]
    system_prompt: str
    estimated_tokens: int
    budget_report: BudgetReport
    compacted_messages: list[dict] | None = None


class PromptAssembler:
    """
    Prompt 组装管线。替代直接调用 engine.assemble() 的位置。

    参数：
        engine:       ContextEngine 实例（负责压缩和 token 预算控制）
        hooks:        HookRunner 实例（用于 before_prompt_build）
        token_budget: 总 token 预算（与 engine 对齐）
    """

    def __init__(
        self,
        engine: "ContextEngine",
        hooks: "HookRunner",
        token_budget: int = 120_000,
    ) -> None:
        self._engine = engine
        self._hooks = hooks
        self._token_budget = token_budget

    async def assemble(
        self,
        session_id: str,
        messages: list[dict],
        current_query: str,
        channel: str | None = None,
        chat_id: str | None = None,
        media: list[str] | None = None,
        attachments: list[Any] | None = None,
        available_tools: set[str] | None = None,
        prompt_mode: str = "full",
        extra_suffix_messages: list[dict] | None = None,
        runtime_instruction: str = "",
    ) -> AssemblerResult:
        """
        执行完整 Prompt 组装管线：

        1. 触发 before_prompt_build hook（取 prepend/append 注入）
        2. 调用 engine.assemble()（透传 hook 输出）
        3. 生成预算报告
        4. 返回 AssemblerResult
        """
        from auraeve.plugins.base import HookBeforePromptBuildEvent

        # ── Step 1: before_prompt_build hook ──────────────────────────────
        prepend_context: str | None = None
        append_context: str | None = None
        try:
            hook_event = HookBeforePromptBuildEvent(
                session_id=session_id,
                channel=channel,
                chat_id=chat_id,
                current_query=current_query,
            )
            hook_result = await self._hooks.run_before_prompt_build(hook_event)
            prepend_context = hook_result.prepend_context or None
            append_context = hook_result.append_context or None
            if prepend_context or append_context:
                logger.debug(
                    f"[assembler] before_prompt_build hook 注入："
                    f"prepend={bool(prepend_context)}, append={bool(append_context)}"
                )
        except Exception as e:
            logger.error(f"[assembler] before_prompt_build hook 失败：{e}")

        # ── Step 2: engine.assemble()（含压缩逻辑）────────────────────────
        assemble_result: AssembleResult = await self._engine.assemble(
            session_id=session_id,
            messages=messages,
            current_query=current_query,
            channel=channel,
            chat_id=chat_id,
            media=media,
            attachments=attachments,
            available_tools=available_tools,
            prompt_mode=prompt_mode,
            prepend_context=prepend_context,
            append_context=append_context,
        )

        # ── Step 3: 提取 system_prompt，生成预算报告 ─────────────────────
        system_prompt = ""
        if assemble_result.messages and assemble_result.messages[0].get("role") == "system":
            system_prompt = assemble_result.messages[0].get("content", "")

        segments = _make_segments(system_prompt, prepend_context, append_context)
        budget_report = BudgetReport.build(segments, self._token_budget)

        if budget_report.utilization > 0.8:
            logger.debug(f"[assembler] {budget_report.summary()}")

        final_messages = assemble_result.messages

        # 注入 runtime_instruction 到 system 消息末尾（不持久化，仅本次 LLM 调用）
        if runtime_instruction and final_messages and final_messages[0].get("role") == "system":
            final_messages = list(final_messages)  # 避免修改原列表
            final_messages[0] = {
                **final_messages[0],
                "content": (final_messages[0].get("content") or "").rstrip()
                           + f"\n\n[运行时内部约束]\n{runtime_instruction}",
            }

        # 追加 synthetic tool_use + tool_result（不持久化，仅本次 LLM 调用）
        if extra_suffix_messages:
            final_messages = final_messages + extra_suffix_messages

        return AssemblerResult(
            messages=final_messages,
            system_prompt=system_prompt,
            estimated_tokens=assemble_result.estimated_tokens,
            budget_report=budget_report,
            compacted_messages=assemble_result.compacted_messages,
        )


def _make_segments(
    system_prompt: str,
    prepend_context: str | None,
    append_context: str | None,
) -> list[PromptSegment]:
    """从 system_prompt 构建分段列表（粗粒度，按 --- 分隔符切割）。"""
    segments: list[PromptSegment] = []

    if prepend_context:
        segments.append(PromptSegment(name="hook_prepend", content=prepend_context))

    # 按 --- 分隔符拆分段落
    raw_parts = system_prompt.split("\n\n---\n\n")
    segment_names = [
        "identity", "protocol_priority", "tooling", "safety", "skills",
        "memory", "workspace", "messaging", "bootstrap",
        "silent_reply", "heartbeat", "runtime",
    ]
    for i, part in enumerate(raw_parts):
        name = segment_names[i] if i < len(segment_names) else f"segment_{i}"
        # 从段落首行提取更具体的名称
        first_line = part.strip().splitlines()[0] if part.strip() else ""
        if first_line.startswith("## "):
            name = first_line[3:].strip().lower().replace(" ", "_")
        segments.append(PromptSegment(name=name, content=part))

    if append_context:
        segments.append(PromptSegment(name="hook_append", content=append_context))

    return segments


def _merge_contexts(*parts: str | None) -> str | None:
    merged = [part.strip() for part in parts if part and part.strip()]
    if not merged:
        return None
    return "\n\n---\n\n".join(merged)
