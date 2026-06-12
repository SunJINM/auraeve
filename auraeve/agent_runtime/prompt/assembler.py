"""PromptAssembler：单层 Prompt 组装管线。

流程：
  1. ContextBuilder 渲染系统提示词并拼装消息（按记忆窗口截取历史）
  2. 生成 BudgetReport（用于 debug/审计）
  3. 注入 runtime_instruction / extra_suffix_messages（仅本次 LLM 调用，不持久化）
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from auraeve.agent.context import ContextBuilder

from .segments import BudgetReport, PromptSegment


@dataclass
class AssemblerResult:
    """PromptAssembler.assemble() 的返回值。"""
    messages: list[dict]
    system_prompt: str
    estimated_tokens: int
    budget_report: BudgetReport


class PromptAssembler:
    """
    Prompt 组装管线。

    参数：
        workspace:           工作区目录（ContextBuilder 渲染提示词用）
        memory_window:       注入模型的最近历史消息条数
        execution_workspace: 命令执行目录（注入提示词）
        token_budget:        总 token 预算（仅用于预算报告）
        context_builder:     可注入的 ContextBuilder（测试用）
    """

    def __init__(
        self,
        workspace: Path | None = None,
        *,
        memory_window: int = 50,
        execution_workspace: str | None = None,
        token_budget: int = 120_000,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        if context_builder is None:
            if workspace is None:
                raise ValueError("PromptAssembler requires workspace or context_builder")
            context_builder = ContextBuilder(workspace, execution_workspace=execution_workspace)
        self._builder = context_builder
        self._memory_window = memory_window
        self._token_budget = token_budget

    @property
    def builder(self) -> ContextBuilder:
        return self._builder

    def set_memory_window(self, window: int) -> None:
        if window > 0:
            self._memory_window = window

    def set_token_budget(self, budget: int) -> None:
        if budget > 0:
            self._token_budget = budget

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
        prepend_context: str | None = None,
        append_context: str | None = None,
    ) -> AssemblerResult:
        """执行完整 Prompt 组装管线。"""
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
        estimated_tokens = sum(
            len(str(m.get("content", ""))) // 4 + 128 for m in assembled
        )

        system_prompt = ""
        if assembled and assembled[0].get("role") == "system":
            system_prompt = assembled[0].get("content", "")

        segments = _make_segments(system_prompt, prepend_context, append_context)
        budget_report = BudgetReport.build(segments, self._token_budget)
        if budget_report.utilization > 0.8:
            logger.debug(f"[assembler] {budget_report.summary()}")

        final_messages = assembled

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
            estimated_tokens=estimated_tokens,
            budget_report=budget_report,
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
        segments.append(PromptSegment(name="append_context", content=append_context))

    return segments
