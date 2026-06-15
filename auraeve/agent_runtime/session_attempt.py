"""SessionAttemptRunner: one run attempt with tool-call loop execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger

from auraeve import media_store
from auraeve.agent.tools.base import ToolExecutionResult
from auraeve.observability import get_observability
from auraeve.agent_runtime.tool_policy.contracts import PolicyContext
from auraeve.agent_runtime.tool_runtime_context import (
    FileReadStateStore,
    TaskReadStateStore,
    ToolRuntimeContext,
    use_tool_runtime_context,
)
from auraeve.providers.base import ToolCallDeclaration, normalize_tool_call_requests

from .budget import ExecutionBudget, normalize_runtime_execution_config
from .trace import RunTrace

if TYPE_CHECKING:
    from auraeve.agent.tools.registry import ToolRegistry
    from auraeve.agent_runtime.tool_policy.engine import ToolPolicyEngine
    from auraeve.providers.base import LLMProvider


_IMAGE_TOOL_NAME = "generate_image"

_DEFAULT_LOOP_GUARD = {
    "mode": "balanced",
    "fingerprintWindow": 3,
    "repeatBlockThreshold": 3,
    "onRepeat": "warn_inject",  # warn_inject | block_tools | slowdown
    "slowdownBackoffMs": 500,
}

_DATA_URL_RE = re.compile(
    r"data:(?P<mime>[a-zA-Z0-9.+-]+/[a-zA-Z0-9.+-]+);base64,(?P<data>[A-Za-z0-9+/=\s]+)"
)
_BASE64_URI_RE = re.compile(r"base64://(?P<data>[A-Za-z0-9+/=\s]{256,})")

_BUDGET_EXHAUSTED_SUMMARY_PROMPT = (
    "[系统提示] 执行预算已耗尽，无法继续工具调用。"
    "请根据你到目前为止已收集到的所有信息，"
    "立即给出一份尽可能完整、结构化的汇总结果。"
    "优先保证关键事实、分析、风险、未决问题和后续动作完整，不要压成简版。"
    "如有信息缺口，在结尾注明哪些内容未能收集到。"
    "不要提及预算或系统限制，直接输出内容。"
)


def _tool_fingerprint(tool_calls: list[Any]) -> str:
    parts: list[str] = []
    for tc in tool_calls:
        args_hash = hashlib.md5(
            json.dumps(tc.arguments, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:8]
        parts.append(f"{tc.name}:{args_hash}")
    return "|".join(parts)


def _normalize_loop_guard(raw: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(_DEFAULT_LOOP_GUARD)
    if not isinstance(raw, dict):
        return out
    out.update(raw)
    out["fingerprintWindow"] = max(1, int(out.get("fingerprintWindow", 3)))
    out["repeatBlockThreshold"] = max(1, int(out.get("repeatBlockThreshold", 3)))
    out["slowdownBackoffMs"] = max(0, int(out.get("slowdownBackoffMs", 500)))
    if out.get("onRepeat") not in {"warn_inject", "block_tools", "slowdown"}:
        out["onRepeat"] = "warn_inject"
    if out.get("mode") not in {"strict", "balanced", "long_task"}:
        out["mode"] = "balanced"
    return out


@dataclass
class AttemptResult:
    final_content: str | None
    tools_used: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    trace: dict[str, Any] | None = None
    final_images: list[dict[str, str]] = field(default_factory=list)


class SessionAttemptRunner:
    """Shared tool-loop runner for main/sub agent attempts."""

    def __init__(
        self,
        provider: "LLMProvider",
        tools: "ToolRegistry",
        policy: "ToolPolicyEngine",
        checkpoint_drain=None,
        max_iterations: int = 100,
        thinking_budget_tokens: int | None = None,
        runtime_execution: dict[str, Any] | None = None,
        runtime_loop_guard: dict[str, Any] | None = None,
        token_budget: int = 120_000,
    ) -> None:
        self._provider = provider
        self._tools = tools
        self._policy = policy
        self._checkpoint_drain = checkpoint_drain
        self._max_iterations = max_iterations
        self._thinking_budget_tokens = thinking_budget_tokens
        self._token_budget = token_budget
        self._execution_cfg = normalize_runtime_execution_config(
            runtime_execution,
            fallback_max_turns=max_iterations,
        )
        self._loop_guard_cfg = _normalize_loop_guard(runtime_loop_guard)
        self._obs = get_observability()

    def apply_runtime_controls(
        self,
        *,
        max_iterations: int | None = None,
        runtime_execution: dict[str, Any] | None = None,
        runtime_loop_guard: dict[str, Any] | None = None,
        token_budget: int | None = None,
    ) -> None:
        if max_iterations is not None and max_iterations > 0:
            self._max_iterations = max_iterations
        if runtime_execution is not None:
            self._execution_cfg = normalize_runtime_execution_config(
                runtime_execution,
                fallback_max_turns=self._max_iterations,
            )
        if runtime_loop_guard is not None:
            self._loop_guard_cfg = _normalize_loop_guard(runtime_loop_guard)
        if token_budget is not None and token_budget > 0:
            self._token_budget = token_budget

    async def _summarize_on_budget_exhausted(
        self,
        msgs: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tool_calls_used: int,
        is_subagent: bool,
    ) -> str:
        """预算耗尽时的收尾：子体用已有上下文做一次汇总，失败或主体则返回兜底文案。"""
        if is_subagent:
            try:
                msgs.append({"role": "user", "content": _BUDGET_EXHAUSTED_SUMMARY_PROMPT})
                summary_response = await self._provider.chat(
                    messages=msgs,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=[],
                )
                if summary_response.content:
                    return summary_response.content
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[session_attempt] 子体预算耗尽汇总失败: {exc}")
        return (
            f"[预算耗尽] 已完成 {tool_calls_used} 次工具调用，"
            "但未能在预算内完成全部搜集。请参考其他子体的结果。"
        )

    async def _maybe_compact_context(
        self,
        msgs: list[dict[str, Any]],
        thread_id: str,
        channel: str | None,
    ) -> list[dict[str, Any]]:
        """每轮调用模型前按 token 预算阈值主动压缩上下文（统一入口见 compaction 模块）。"""
        from auraeve.agent_runtime.compaction import proactive_compact

        outcome = await proactive_compact(msgs, self._token_budget, self._provider)
        if outcome.stage == "tools_cleared":
            self._obs.emit(
                level="info",
                kind="trace",
                subsystem="runtime/compaction",
                message="tool_results_cleared",
                attrs={"tokensAfter": outcome.tokens_after},
                session_key=thread_id,
                channel=channel,
            )
        elif outcome.stage == "summarized":
            self._obs.emit(
                level="info",
                kind="trace",
                subsystem="runtime/compaction",
                message="context_compacted",
                attrs={"tokensBefore": outcome.tokens_before, "tokensAfter": outcome.tokens_after},
                session_key=thread_id,
                channel=channel,
            )
        return outcome.messages

    async def run(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: "ToolRegistry | None" = None,
        thread_id: str = "",
        channel: str | None = None,
        chat_id: str | None = None,
        is_subagent: bool = False,
        steer_queue: asyncio.Queue | None = None,
    ) -> AttemptResult:
        msgs = list(messages)
        active_tools = tools or self._tools
        final_content: str | None = None
        tools_used: list[str] = []
        # 本次运行累积的图片引用：统一在最终回复后一次性展示（不在工具块处展示，避免重复）。
        pending_image_refs: list[dict[str, str]] = []
        recent_fingerprints: list[str] = []
        transcript_messages: list[dict[str, Any]] = []
        file_reads = FileReadStateStore()
        runtime_context = ToolRuntimeContext(
            file_reads=file_reads,
            task_reads=TaskReadStateStore(),
        )

        budget = ExecutionBudget(self._execution_cfg)
        trace = RunTrace(session_id=thread_id, is_subagent=is_subagent)

        while True:
            can_start, reason = budget.check_turn_budget()
            if not can_start:
                trace.stop_reason = reason
                trace.add("budget_exhausted", reason=reason, snapshot=budget.snapshot())
                final_content = await self._summarize_on_budget_exhausted(
                    msgs, model, temperature, max_tokens,
                    tool_calls_used=budget.tool_calls_used,
                    is_subagent=is_subagent,
                )
                break

            budget.mark_turn_started()
            trace.add("turn_started", turn=budget.turns_used)

            if is_subagent and steer_queue is not None:
                while not steer_queue.empty():
                    try:
                        steer_msg = steer_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    steer_message = {"role": "user", "content": f"[引导消息] {steer_msg}"}
                    msgs.append(steer_message)
                    transcript_messages.append(steer_message)
                    trace.add("steer_injected", message=str(steer_msg)[:200])

            effective_model = model
            if self._checkpoint_drain is not None:
                drained_messages = self._checkpoint_drain(
                    thread_id=thread_id,
                    is_subagent=is_subagent,
                )
                if drained_messages:
                    msgs.extend(drained_messages)

            async def _text_delta_cb(delta: str) -> None:
                self._obs.emit(
                    level="info",
                    kind="event",
                    subsystem="runtime/assistant",
                    message="assistant_text_delta",
                    attrs={"delta": delta},
                    session_key=thread_id,
                    channel=channel,
                    persist=False,
                )

            async def _tool_call_declared_cb(declaration: ToolCallDeclaration) -> None:
                self._obs.emit(
                    level="info",
                    kind="event",
                    subsystem="runtime/tools",
                    message="tool_call_declared",
                    attrs={
                        "toolName": declaration.name,
                        "toolCallId": declaration.id,
                        "argsPreview": _safe_json(declaration.arguments) if declaration.arguments is not None else "",
                        "streamIndex": declaration.index,
                        "isSubagent": bool(is_subagent),
                    },
                    session_key=thread_id,
                    channel=channel,
                    persist=False,
                )

            # 主动压缩：每轮调用模型前按 token 预算阈值压缩上下文
            msgs = await self._maybe_compact_context(msgs, thread_id, channel)

            response = await self._provider.chat(
                messages=msgs,
                tools=active_tools.get_definitions(),
                model=effective_model,
                temperature=temperature,
                max_tokens=max_tokens,
                thinking_budget_tokens=self._thinking_budget_tokens,
                text_delta_callback=_text_delta_cb,
                tool_call_declared_callback=_tool_call_declared_cb,
            )

            # 模型原生出图：落盘为短引用并累积，统一到最终回复后展示；图片二进制不入上下文。
            if getattr(response, "images", None):
                try:
                    refs = media_store.refs_from_images_field(response.images)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"[session_attempt] 原生图片落盘失败: {exc}")
                    refs = []
                if refs:
                    pending_image_refs.extend(refs)

            if not response.has_tool_calls:
                has_text = response.content is not None and bool(str(response.content).strip())
                if not has_text and not pending_image_refs:
                    logger.warning(
                        "[session_attempt] empty assistant response without tool calls; "
                        f"finish_reason={response.finish_reason} "
                        f"reasoning_content={bool(response.reasoning_content)}"
                    )
                    final_content = None
                    trace.stop_reason = "empty_response"
                    trace.add("empty_response", finish_reason=response.finish_reason)
                    break
                # 移除模型自行嵌入的 media 图片 markdown，避免与下方 image 块重复展示。
                final_content = _strip_media_image_markdown(response.content or "")
                if pending_image_refs:
                    self._obs.emit(
                        level="info",
                        kind="event",
                        subsystem="runtime/image",
                        message="image_ready",
                        attrs={"images": pending_image_refs},
                        session_key=thread_id,
                        channel=channel,
                        persist=False,
                    )
                trace.stop_reason = "model_completed"
                trace.add("model_completed", finish_reason=response.finish_reason)
                break

            tool_calls = normalize_tool_call_requests(list(response.tool_calls))
            fp = _tool_fingerprint(tool_calls)
            recent_fingerprints.append(fp)
            window = int(self._loop_guard_cfg["fingerprintWindow"])
            repeat_threshold = int(self._loop_guard_cfg["repeatBlockThreshold"])
            if len(recent_fingerprints) > max(window, repeat_threshold):
                recent_fingerprints.pop(0)

            repeated = (
                len(recent_fingerprints) >= repeat_threshold
                and len(set(recent_fingerprints[-repeat_threshold:])) == 1
            )
            if repeated:
                mode = self._loop_guard_cfg["onRepeat"]
                trace.add("loop_detected", fingerprint=fp, action=mode)
                if mode == "slowdown":
                    await asyncio.sleep(int(self._loop_guard_cfg["slowdownBackoffMs"]) / 1000)
                elif mode == "block_tools":
                    tool_call_dicts = _make_tool_call_dicts(tool_calls)
                    before_len = len(msgs)
                    msgs = _add_assistant_msg(msgs, response.content, tool_call_dicts, response.reasoning_content)
                    transcript_messages.extend(msgs[before_len:])
                    for tc in tool_calls:
                        before_len = len(msgs)
                        msgs = _add_tool_result(msgs, tc.id, tc.name, "[工具调用被跳过：检测到重复循环]")
                        transcript_messages.extend(msgs[before_len:])
                    msgs.append(
                        {
                            "role": "user",
                            "content": "检测到重复工具调用，请改变策略或说明阻塞点。",
                        }
                    )
                    continue
                else:
                    msgs.append(
                        {
                            "role": "user",
                            "content": "检测到你连续重复调用同一组工具，请换一种方式完成任务。",
                        }
                    )

            admitted = budget.admit_tool_calls(len(tool_calls))
            if admitted <= 0:
                trace.stop_reason = "max_tool_calls_exhausted"
                trace.add("budget_exhausted", reason="max_tool_calls_exhausted", snapshot=budget.snapshot())
                final_content = await self._summarize_on_budget_exhausted(
                    msgs, model, temperature, max_tokens,
                    tool_calls_used=budget.tool_calls_used,
                    is_subagent=is_subagent,
                )
                break
            if admitted < len(tool_calls):
                trace.add("tool_calls_truncated", requested=len(tool_calls), admitted=admitted)
                tool_calls = tool_calls[:admitted]

            tool_call_dicts = _make_tool_call_dicts(tool_calls)
            before_len = len(msgs)
            msgs = _add_assistant_msg(msgs, response.content, tool_call_dicts, response.reasoning_content)
            transcript_messages.extend(msgs[before_len:])
            if response.content and str(response.content).strip():
                self._obs.emit(
                    level="info",
                    kind="event",
                    subsystem="runtime/assistant",
                    message="assistant_text",
                    attrs={
                        "content": response.content,
                        "contentLength": len(str(response.content)),
                        "isSubagent": bool(is_subagent),
                    },
                    session_key=thread_id,
                    channel=channel,
                )
            for tc in tool_calls:
                tools_used.append(tc.name)

            semaphore = asyncio.Semaphore(self._execution_cfg.tool_concurrency)
            tool_timeout_s = self._execution_cfg.tool_timeout_ms / 1000

            async def _exec(tc: Any) -> tuple[Any, Any, dict[str, Any]]:
                async with semaphore:
                    args_str = _safe_json(tc.arguments)
                    logger.debug(f"准备执行工具：{tc.name}，参数预览：{args_str[:200]}")
                    started_at = time.perf_counter()
                    tool_meta = active_tools.get_metadata(tc.name)
                    meta_group = None
                    if isinstance(tool_meta, dict):
                        meta_group = tool_meta.get("group")
                    tool_group = (
                        str(meta_group).strip()
                        if isinstance(meta_group, str) and str(meta_group).strip()
                        else self._policy.infer_tool_group(tc.name)
                    )
                    mcp_server = None
                    if isinstance(tool_meta, dict):
                        mcp_meta = tool_meta.get("mcp")
                        if isinstance(mcp_meta, dict):
                            mcp_server = str(mcp_meta.get("server_id") or "").strip() or None

                    self._obs.emit(
                        level="info",
                        kind="event",
                        subsystem="runtime/tools",
                        message="tool_call_started",
                        attrs={
                            "toolName": tc.name,
                            "toolCallId": getattr(tc, "id", None),
                            "toolGroup": tool_group,
                            "argsPreview": _truncate_text(args_str, 500),
                            "isSubagent": bool(is_subagent),
                            "mcpServer": mcp_server,
                        },
                        session_key=thread_id,
                        channel=channel,
                    )

                    policy_ctx = PolicyContext(
                        tool_name=tc.name,
                        args=tc.arguments,
                        session_id=thread_id,
                        channel=channel,
                        chat_id=chat_id,
                        is_subagent=is_subagent,
                        tool_group=tool_group,
                        mcp_server=mcp_server,
                        tool_metadata=tool_meta,
                    )
                    policy_result = await self._policy.evaluate(policy_ctx)
                    if not policy_result.allowed:
                        duration_ms = int((time.perf_counter() - started_at) * 1000)
                        self._obs.emit(
                            level="warn",
                            kind="event",
                            subsystem="runtime/tools",
                            message="tool_call_policy_denied",
                            attrs={
                                "toolName": tc.name,
                                "toolCallId": getattr(tc, "id", None),
                                "toolGroup": tool_group,
                                "status": "policy_denied",
                                "durationMs": duration_ms,
                                "reason": policy_result.reason,
                            },
                            session_key=thread_id,
                            channel=channel,
                        )
                        return tc, f"[工具调用被策略拒绝：{policy_result.reason}]", {
                            "status": "policy_denied",
                            "errorKind": "policy_denied",
                            "durationMs": duration_ms,
                        }
                    effective_args = policy_result.rewritten_args

                    async def _run_tool() -> Any:
                        tool_obj = active_tools.get(tc.name)
                        try:
                            if tool_obj is not None:
                                setattr(tool_obj, "_current_tool_call_id", tc.id)
                            with use_tool_runtime_context(runtime_context):
                                result = await active_tools.execute(tc.name, effective_args)
                        except Exception as exc:  # noqa: BLE001
                            result = f"工具执行出错：{exc}"
                        finally:
                            if tool_obj is not None and hasattr(tool_obj, "_current_tool_call_id"):
                                setattr(tool_obj, "_current_tool_call_id", "")
                        return result

                    effective_timeout_s = tool_timeout_s
                    if isinstance(tool_meta, dict):
                        meta_timeout = tool_meta.get("timeout_ms")
                        if isinstance(meta_timeout, (int, float)) and meta_timeout > 0:
                            effective_timeout_s = meta_timeout / 1000

                    status = "success"
                    error_kind = ""
                    try:
                        raw_result = await asyncio.wait_for(_run_tool(), timeout=effective_timeout_s)
                    except asyncio.TimeoutError:
                        status = "timeout"
                        error_kind = "timeout"
                        raw_result = f"工具执行超时：{int(effective_timeout_s * 1000)}ms"
                    else:
                        status, error_kind = _classify_tool_result(_tool_result_text(raw_result))

                    result_text = _tool_result_text(raw_result)

                    duration_ms = int((time.perf_counter() - started_at) * 1000)
                    self._obs.emit(
                        level="info" if status == "success" else ("error" if status == "failed" else "warn"),
                        kind="event",
                        subsystem="runtime/tools",
                        message="tool_call_completed",
                        attrs={
                            "toolName": tc.name,
                            "toolCallId": getattr(tc, "id", None),
                            "toolGroup": tool_group,
                            "status": status,
                            "errorKind": error_kind or None,
                            "durationMs": duration_ms,
                            "resultLength": len(result_text),
                            "resultPreview": _truncate_text(result_text, 800),
                        },
                        session_key=thread_id,
                        channel=channel,
                    )

                    return tc, raw_result, {
                        "status": status,
                        "errorKind": error_kind,
                        "durationMs": duration_ms,
                    }

            results = await asyncio.gather(*[_exec(tc) for tc in tool_calls])
            budget.consume_tool_calls(len(results))
            success_count = sum(1 for _tc, _result, meta in results if meta.get("status") == "success")
            failed_count = len(results) - success_count
            self._obs.emit(
                level="info" if failed_count == 0 else "warn",
                kind="event",
                subsystem="runtime/tools",
                message="tool_batch_summary",
                attrs={
                    "count": len(results),
                    "successCount": success_count,
                    "failedCount": failed_count,
                    "toolNames": [tc.name for tc in tool_calls],
                    "snapshot": budget.snapshot(),
                },
                session_key=thread_id,
                channel=channel,
            )
            trace.add(
                "tool_batch_completed",
                count=len(results),
                snapshot=budget.snapshot(),
            )

            for tc, result, meta in results:
                compact_result = _compact_tool_result(tc.name, _tool_result_content(result))
                image_refs = None
                if isinstance(result, ToolExecutionResult) and isinstance(result.data, dict):
                    image_refs = result.data.get("image_refs") or None
                before_len = len(msgs)
                msgs = _add_tool_result(msgs, tc.id, tc.name, compact_result)
                transcript_messages.extend(msgs[before_len:])
                if meta.get("status") != "success":
                    msgs[-1] = {
                        **msgs[-1],
                        "error_kind": meta.get("errorKind") or None,
                        "duration_ms": meta.get("durationMs"),
                    }
                if image_refs:
                    # 累积，统一在最终回复后展示一次（缩略图块）。
                    pending_image_refs.extend(image_refs)
                elif tc.name == _IMAGE_TOOL_NAME:
                    # 图片工具未产出图片（失败/超时）：结束前端占位动画，置为错误态。
                    self._obs.emit(
                        level="warn",
                        kind="event",
                        subsystem="runtime/image",
                        message="image_failed",
                        attrs={
                            "toolCallId": getattr(tc, "id", None),
                            "error": _truncate_text(_tool_result_text(result), 200),
                        },
                        session_key=thread_id,
                        channel=channel,
                        persist=False,
                    )
                if isinstance(result, ToolExecutionResult) and result.extra_messages:
                    msgs.extend(result.extra_messages)

            if self._execution_cfg.tool_failure_policy == "fail_fast" and failed_count > 0:
                final_content = f"任务中止：工具批次失败（{failed_count}/{len(results)}）。"
                trace.stop_reason = "tool_batch_failed"
                trace.add("tool_batch_failed", failed=failed_count, total=len(results))
                break

        return AttemptResult(
            final_content=final_content,
            tools_used=tools_used,
            messages=transcript_messages,
            trace=trace.to_dict(),
            final_images=pending_image_refs,
        )


def _make_tool_call_dicts(tool_calls: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": tc.id,
            "type": "function",
            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
        }
        for tc in tool_calls
    ]


def _add_assistant_msg(
    messages: list[dict[str, Any]],
    content: str | None,
    tool_calls: list[dict[str, Any]] | None = None,
    reasoning_content: str | None = None,
) -> list[dict[str, Any]]:
    msg: dict[str, Any] = {"role": "assistant", "content": content or ""}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    if reasoning_content:
        msg["reasoning_content"] = reasoning_content
    messages.append(msg)
    return messages


def _add_tool_result(
    messages: list[dict[str, Any]],
    tool_call_id: str,
    tool_name: str,
    result: Any,
) -> list[dict[str, Any]]:
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result,
        }
    )
    return messages


_MEDIA_IMG_MD_RE = re.compile(r"!\[[^\]]*\]\(\s*[^)\s]*?/api/webui/media/[^)\s]*\s*\)")


def _strip_media_image_markdown(content: str) -> str:
    """移除模型自行嵌入的、指向本地 media 的图片 markdown，避免与 image 块重复展示。"""
    if not content:
        return content
    cleaned = _MEDIA_IMG_MD_RE.sub("", content)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _safe_json(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return str(data)


def _truncate_text(value: Any, max_len: int = 600) -> str:
    text = str(value or "")
    if len(text) <= max_len:
        return text
    return f"{text[:max_len]}...(truncated,{len(text)} chars)"


def _classify_tool_result(result_text: str) -> tuple[str, str]:
    text = (result_text or "").strip()
    if not text:
        return "success", ""
    if text.startswith("[工具调用被策略拒绝："):
        return "policy_denied", "policy_denied"
    if text.startswith("[工具调用被拦截："):
        return "hook_blocked", "hook_blocked"
    if text.startswith("工具执行超时："):
        return "timeout", "timeout"
    if text.startswith("工具执行出错："):
        return "failed", "tool_exception"
    return "success", ""


def _tool_result_content(result: Any) -> Any:
    if isinstance(result, ToolExecutionResult):
        return result.content
    return result


def _tool_result_text(result: Any) -> str:
    return str(_tool_result_content(result) or "")


def _compact_tool_result(tool_name: str, result_text: Any) -> Any:
    if isinstance(result_text, list):
        return result_text
    text = str(result_text or "")
    text = _replace_embedded_binary(text)
    return text


def _replace_embedded_binary(text: str) -> str:
    def _replace_data_url(match: re.Match[str]) -> str:
        mime = match.group("mime")
        b64 = match.group("data")
        approx_bytes = int(len("".join(b64.split())) * 0.75)
        return f"[inline-data-url omitted mime={mime} approx_bytes={approx_bytes}]"

    def _replace_base64_uri(match: re.Match[str]) -> str:
        b64 = match.group("data")
        approx_bytes = int(len("".join(b64.split())) * 0.75)
        return f"[inline-base64-uri omitted approx_bytes={approx_bytes}]"

    text = _DATA_URL_RE.sub(_replace_data_url, text)
    text = _BASE64_URI_RE.sub(_replace_base64_uri, text)
    return text
