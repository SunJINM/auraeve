"""
上下文压缩算法与统一压缩入口。

实现：
- Token 估算（tiktoken 精确 / char/4 降级）
- 分块（按 token 预算）
- LLM 顺序摘要 + 多块合并
- 标识符保全（UUID、哈希、API密钥等不得缩写）

统一入口（system 消息切分在此处理，调用方不再各自切分）：
- proactive_compact()：先做工具结果清理，仍超阈值再 LLM 摘要兜底
- compact_history_for_overflow()：上下文溢出异常恢复时的强制摘要
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from auraeve.providers.base import LLMProvider

from auraeve.providers.base import backfill_tool_context_start


@dataclass
class CompactResult:
    """compact_messages() 返回值。"""
    ok: bool
    compacted: bool
    compacted_messages: list[dict] | None = None
    tokens_before: int = 0
    tokens_after: int = 0
    summary: str = ""
    reason: str = ""


@dataclass
class ProactiveCompactOutcome:
    """proactive_compact() 返回值。stage 标识实际执行到哪一层。"""
    messages: list[dict]
    stage: str  # "none" | "tools_cleared" | "summarized"
    tokens_before: int = 0
    tokens_after: int = 0

# ── 常量 ─────────────────────────────────────────────────────

SAFETY_MARGIN = 1.2          # token 估算安全边际（补偿 heuristic 误差）
BASE_CHUNK_RATIO = 0.4       # 每个分块占 token 预算的比例
KEEP_RATIO = 0.2             # 末尾保留比例（不参与压缩）
KEEP_MIN = 10                # 至少保留的消息条数

IDENTIFIER_PRESERVATION = (
    "保留所有标识符完全不变（不得缩写或重构）："
    "UUID、哈希值、token、API密钥、IP地址、端口号、域名、文件路径、版本号等。"
)

_MERGE_PROMPT = """请将以下多个部分摘要合并为一个连贯、完整、结构化的摘要。

必须保留：
- 活跃任务及其当前状态（进行中、已阻塞、待处理）
- 批量操作进度（如"5/17项已完成"）
- 最后一个用户请求及处理进展
- 做出的决策及其依据
- 待办事项、开放问题、约束条件
- 承诺的后续跟进

优先保留近期上下文，Agent 需要知道它正在做什么，而不仅仅是讨论过什么。
在完整性的前提下保持清晰，避免空泛压缩。
允许使用简洁的 Markdown 标题或项目符号来保持结构。

{identifier_instruction}

以下是各部分摘要：

{summaries}
"""

_CHUNK_PROMPT = """请将以下对话历史压缩为高保真、结构化摘要。{prev_context}

必须保留：
- 所有活跃任务及其状态
- 重要的决策和依据
- 待处理的问题和约束
- 批量操作的进度

{identifier_instruction}

对话内容：
{conversation}
"""

# ── Token 估算 ────────────────────────────────────────────────

_tiktoken_enc = None
_CL100K_PAT_STR = (
    r"""'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| """
    r"""?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s"""
)
_CL100K_SPECIAL_TOKENS = {
    "<|endoftext|>": 100257,
    "<|fim_prefix|>": 100258,
    "<|fim_middle|>": 100259,
    "<|fim_suffix|>": 100260,
    "<|endofprompt|>": 100276,
}


def _resolve_project_root() -> Path:
    # compaction.py -> agent_runtime -> auraeve(package) -> project root
    return Path(__file__).resolve().parents[2]


def _resolve_local_tiktoken_file() -> Path:
    return _resolve_project_root() / "resources" / "tiktoken" / "cl100k_base.tiktoken"


def _get_tiktoken():
    global _tiktoken_enc
    if _tiktoken_enc is None:
        try:
            import tiktoken
            local_file = _resolve_local_tiktoken_file()
            if local_file.exists() and local_file.is_file():
                try:
                    from tiktoken.load import load_tiktoken_bpe

                    mergeable_ranks = load_tiktoken_bpe(str(local_file))
                    _tiktoken_enc = tiktoken.Encoding(
                        name="cl100k_base_local",
                        pat_str=_CL100K_PAT_STR,
                        mergeable_ranks=mergeable_ranks,
                        special_tokens=_CL100K_SPECIAL_TOKENS,
                    )
                    logger.debug(f"已加载本地 tiktoken 词表：{local_file}")
                    return _tiktoken_enc
                except Exception as exc:
                    logger.warning(f"[tiktoken] local vocabulary load failed, fallback to default: {exc}")

            cache_dir = local_file.parent
            if cache_dir.exists() and cache_dir.is_dir():
                os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(cache_dir))

            _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _tiktoken_enc = False
    return _tiktoken_enc if _tiktoken_enc is not False else None


def estimate_tokens(messages: list[dict]) -> int:
    """
    估算消息列表的 token 数。

    优先使用 tiktoken（精确），降级到 char/4 启发式。
    每条消息加 128 个固定开销（role、metadata、格式化）。
    """
    enc = _get_tiktoken()
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, list):
            content = " ".join(
                c.get("text", "") for c in content if isinstance(c, dict)
            )
        # 计算 tool_calls 字段（assistant 消息中工具调用的 JSON 内容）
        tool_calls = msg.get("tool_calls")
        tool_calls_text = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else ""

        combined = content + tool_calls_text
        if enc:
            try:
                total += len(enc.encode(combined))
            except Exception:
                total += len(combined) // 4
        else:
            total += len(combined) // 4
        total += 128  # role + metadata 开销
    return total


def should_compact(
    messages: list[dict],
    budget: int,
    threshold_ratio: float = 0.85,
) -> bool:
    """判断是否需要压缩（估算 token × 安全边际 > 预算 × 阈值比）。"""
    estimated = estimate_tokens(messages) * SAFETY_MARGIN
    return estimated > budget * threshold_ratio


def clear_tool_results(
    messages: list[dict],
    keep_recent: int = 6,
    min_chars: int = 600,
) -> list[dict]:
    """工具结果清理：最轻量、可恢复的压缩（Anthropic「tool-result clearing」）。

    将较早且体量较大的工具结果正文替换为占位提示，保留 role/tool_call_id/name 等结构字段，
    保留最近 keep_recent 个工具结果原文。智能体如再次需要可重新调用对应工具获取，信息可恢复。
    不调用 LLM，几乎零成本，应作为压缩的第一层。
    """
    tool_positions = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    if len(tool_positions) <= keep_recent:
        return messages

    elide_before = tool_positions[-keep_recent]
    out: list[dict] = []
    for i, m in enumerate(messages):
        content = m.get("content")
        if (
            i < elide_before
            and m.get("role") == "tool"
            and isinstance(content, str)
            and len(content) > min_chars
        ):
            cleared = dict(m)
            cleared["content"] = (
                f"[工具结果已清理以节省上下文（原 {len(content)} 字符）；"
                "如需该结果请重新调用对应工具。]"
            )
            out.append(cleared)
        else:
            out.append(m)
    return out


# ── 消息分块 ──────────────────────────────────────────────────


def _split_messages_by_token_budget(
    messages: list[dict], max_tokens: int
) -> list[list[dict]]:
    """将消息列表按 token 上限分块。"""
    effective_max = max(1, int(max_tokens / SAFETY_MARGIN))
    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_tokens = 0

    for msg in messages:
        msg_tokens = estimate_tokens([msg])
        if current and current_tokens + msg_tokens > effective_max:
            chunks.append(current)
            current = []
            current_tokens = 0
        current.append(msg)
        current_tokens += msg_tokens
        if msg_tokens > effective_max:
            # 单条消息超限，独立成块
            chunks.append(current)
            current = []
            current_tokens = 0

    if current:
        chunks.append(current)
    return chunks


# ── LLM 摘要 ──────────────────────────────────────────────────


def _format_messages_for_summary(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content") or ""
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        if not content:
            continue
        label = {"user": "用户", "assistant": "助手", "system": "系统"}.get(role, role)
        lines.append(f"[{label}] {content[:1000]}")
    return "\n".join(lines)


async def _summarize_chunk(
    chunk: list[dict],
    provider: "LLMProvider",
    prev_summary: str,
    identifier_instruction: str,
) -> str:
    prev_context = (
        f"\n\n（参考之前的摘要：{prev_summary[:500]}）" if prev_summary else ""
    )
    conversation = _format_messages_for_summary(chunk)
    prompt = _CHUNK_PROMPT.format(
        prev_context=prev_context,
        identifier_instruction=identifier_instruction,
        conversation=conversation,
    )
    try:
        response = await provider.chat(
            messages=[
                {"role": "system", "content": "你是对话摘要 Agent，请按要求输出结构化摘要，优先保证信息完整和层次清楚，可使用简洁 Markdown。"},
                {"role": "user", "content": prompt},
            ],
        )
        return (response.content or "").strip()
    except Exception as e:
        logger.warning(f"摘要生成失败：{e}")
        return f"[摘要失败：{e}]"


async def _merge_summaries(
    summaries: list[str],
    provider: "LLMProvider",
    identifier_instruction: str,
) -> str:
    formatted = "\n\n---\n\n".join(f"第{i+1}部分：\n{s}" for i, s in enumerate(summaries))
    prompt = _MERGE_PROMPT.format(
        identifier_instruction=identifier_instruction,
        summaries=formatted,
    )
    try:
        response = await provider.chat(
            messages=[
                {"role": "system", "content": "你是摘要合并 Agent，请输出结构化摘要，优先保证信息完整和层次清楚，可使用简洁 Markdown。"},
                {"role": "user", "content": prompt},
            ],
        )
        return (response.content or "").strip()
    except Exception as e:
        logger.warning(f"摘要合并失败：{e}")
        return "\n\n".join(summaries)


# ── 主压缩入口 ────────────────────────────────────────────────


async def compact_messages(
    messages: list[dict],
    budget: int,
    provider: "LLMProvider",
    custom_instructions: str = "",
) -> CompactResult:
    """
    将 messages 压缩为摘要 + 末尾保留消息。

    流程：
    1. 计算保留末尾 KEEP_RATIO（至少 KEEP_MIN 条）
    2. 将待压缩部分按 budget × BASE_CHUNK_RATIO 分块
    3. 顺序调用 LLM 摘要（后块以前块摘要为上下文）
    4. 多块时合并摘要
    5. 返回 [摘要消息] + 末尾保留消息
    """
    if not messages:
        return CompactResult(ok=False, compacted=False, reason="消息为空")

    keep_count = max(KEEP_MIN, int(len(messages) * KEEP_RATIO))
    if len(messages) <= keep_count:
        return CompactResult(ok=False, compacted=False, reason="消息数量不足以压缩")

    keep_start = max(len(messages) - keep_count, 0)
    keep_start = backfill_tool_context_start(messages, keep_start)
    to_summarize = messages[:keep_start]
    to_keep = messages[keep_start:]
    tokens_before = estimate_tokens(messages)

    identifier_instruction = IDENTIFIER_PRESERVATION
    if custom_instructions:
        identifier_instruction += f"\n\n额外要求：\n{custom_instructions}"

    max_chunk_tokens = int(budget * BASE_CHUNK_RATIO)
    chunks = _split_messages_by_token_budget(to_summarize, max_chunk_tokens)

    if not chunks:
        return CompactResult(ok=False, compacted=False, reason="无可压缩内容")

    logger.debug(f"上下文压缩开始：{len(to_summarize)} 条消息分为 {len(chunks)} 块")

    # 顺序摘要
    summaries: list[str] = []
    prev_summary = ""
    for i, chunk in enumerate(chunks):
        logger.debug(f"正在摘要第 {i+1}/{len(chunks)} 块（{len(chunk)} 条消息）")
        summary = await _summarize_chunk(chunk, provider, prev_summary, identifier_instruction)
        summaries.append(summary)
        prev_summary = summary

    # 合并
    if len(summaries) > 1:
        logger.debug(f"正在合并 {len(summaries)} 个部分摘要")
        final_summary = await _merge_summaries(summaries, provider, identifier_instruction)
    else:
        final_summary = summaries[0]

    summary_message = {
        "role": "user",
        "content": (
            "[以下是此前对话的压缩摘要，原始消息已归档]\n\n"
            f"{final_summary}"
        ),
    }

    compacted = [summary_message] + list(to_keep)
    tokens_after = estimate_tokens(compacted)

    logger.info(f"上下文压缩完成：{tokens_before} → {tokens_after} tokens")

    return CompactResult(
        ok=True,
        compacted=True,
        compacted_messages=compacted,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        summary=final_summary,
    )


# ── 统一压缩入口 ──────────────────────────────────────────────


def _split_system(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    system_msgs = [m for m in messages if m.get("role") == "system"]
    history = [m for m in messages if m.get("role") != "system"]
    return system_msgs, history


async def proactive_compact(
    messages: list[dict],
    budget: int,
    provider: "LLMProvider",
) -> ProactiveCompactOutcome:
    """主动上下文压缩（Anthropic 上下文工程）：接近预算阈值时先做工具结果清理，
    仍超阈值再做 LLM 摘要兜底。只压缩送入模型的上下文，不影响 transcript。"""
    if budget <= 0 or not should_compact(messages, budget):
        return ProactiveCompactOutcome(messages=messages, stage="none")

    tokens_before = estimate_tokens(messages)
    system_msgs, history = _split_system(messages)

    # 第一层：工具结果清理（可恢复、无需 LLM）
    cleared = clear_tool_results(history)
    if not should_compact(system_msgs + cleared, budget):
        return ProactiveCompactOutcome(
            messages=system_msgs + cleared,
            stage="tools_cleared",
            tokens_before=tokens_before,
            tokens_after=estimate_tokens(system_msgs + cleared),
        )

    # 第二层：LLM 摘要兜底
    try:
        result = await compact_messages(cleared, budget, provider)
        if result.compacted and result.compacted_messages:
            return ProactiveCompactOutcome(
                messages=system_msgs + result.compacted_messages,
                stage="summarized",
                tokens_before=result.tokens_before,
                tokens_after=result.tokens_after,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[compaction] 主动压缩 LLM 摘要失败: {exc}")
    return ProactiveCompactOutcome(
        messages=system_msgs + cleared,
        stage="tools_cleared",
        tokens_before=tokens_before,
        tokens_after=estimate_tokens(system_msgs + cleared),
    )


async def compact_history_for_overflow(
    messages: list[dict],
    budget: int,
    provider: "LLMProvider",
) -> list[dict] | None:
    """上下文溢出（provider 抛 ContextOverflowError）后的强制摘要恢复。

    返回压缩后的完整消息列表（含 system）；无法压缩时返回 None。"""
    try:
        system_msgs, history = _split_system(messages)
        if not history:
            return None
        result = await compact_messages(history, budget, provider)
        if result.compacted and result.compacted_messages:
            return system_msgs + result.compacted_messages
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[compaction] 溢出恢复压缩失败: {exc}")
    return None
