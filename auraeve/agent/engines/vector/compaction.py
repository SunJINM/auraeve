"""
上下文压缩算法。

实现：
- Token 估算（tiktoken 精确 / char/4 降级）
- 分块（按 token 预算）
- LLM 顺序摘要 + 多块合并
- 标识符保全（UUID、哈希、API密钥等不得缩写）
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from auraeve.providers.base import LLMProvider

from auraeve.agent.engines.base import CompactResult
from auraeve.providers.base import backfill_tool_context_start

# ── 常量 ─────────────────────────────────────────────────────

SAFETY_MARGIN = 1.2          # token 估算安全边际（补偿 heuristic 误差）
BASE_CHUNK_RATIO = 0.4       # 每个分块占 token 预算的比例
KEEP_RATIO = 0.2             # 末尾保留比例（不参与压缩）
KEEP_MIN = 10                # 至少保留的消息条数

IDENTIFIER_PRESERVATION = (
    "保留所有标识符完全不变（不得缩写或重构）："
    "UUID、哈希值、token、API密钥、IP地址、端口号、域名、文件路径、版本号等。"
)

_MERGE_PROMPT = """请将以下多个部分摘要合并为一个连贯的完整摘要。

必须保留：
- 活跃任务及其当前状态（进行中、已阻塞、待处理）
- 批量操作进度（如"5/17项已完成"）
- 最后一个用户请求及处理进展
- 做出的决策及其依据
- 待办事项、开放问题、约束条件
- 承诺的后续跟进

优先保留近期上下文，Agent 需要知道它正在做什么，而不仅仅是讨论过什么。

{identifier_instruction}

以下是各部分摘要：

{summaries}
"""

_CHUNK_PROMPT = """请将以下对话历史压缩为简洁的摘要。{prev_context}

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
    # compaction.py -> vector -> engines -> agent -> auraeve -> project root
    return Path(__file__).resolve().parents[4]


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
                    logger.info(f"[tiktoken] loaded local vocabulary: {local_file}")
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
                {"role": "system", "content": "你是对话摘要 Agent，请按要求输出纯文本摘要，不使用 Markdown。"},
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
                {"role": "system", "content": "你是摘要合并 Agent，请输出纯文本，不使用 Markdown。"},
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

    logger.info(f"上下文压缩：{len(to_summarize)} 条消息分为 {len(chunks)} 块进行摘要")

    # 顺序摘要
    summaries: list[str] = []
    prev_summary = ""
    for i, chunk in enumerate(chunks):
        logger.info(f"  正在摘要第 {i+1}/{len(chunks)} 块（{len(chunk)} 条消息）…")
        summary = await _summarize_chunk(chunk, provider, prev_summary, identifier_instruction)
        summaries.append(summary)
        prev_summary = summary

    # 合并
    if len(summaries) > 1:
        logger.info(f"  合并 {len(summaries)} 个部分摘要…")
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
