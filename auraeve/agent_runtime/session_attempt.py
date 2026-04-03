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

from auraeve.observability import get_observability
from auraeve.agent_runtime.tool_policy.contracts import PolicyContext
from auraeve.plugins.base import (
    HookAfterToolCallEvent,
    HookBeforeModelResolveEvent,
    HookBeforeToolCallEvent,
)

from .budget import ExecutionBudget, normalize_runtime_execution_config
from .trace import RunTrace

if TYPE_CHECKING:
    from auraeve.agent.tools.registry import ToolRegistry
    from auraeve.agent_runtime.tool_policy.engine import ToolPolicyEngine
    from auraeve.plugins.hooks import HookRunner
    from auraeve.providers.base import LLMProvider


_DEFAULT_LOOP_GUARD = {
    "mode": "balanced",
    "fingerprintWindow": 3,
    "repeatBlockThreshold": 3,
    "onRepeat": "warn_inject",  # warn_inject | block_tools | slowdown
    "slowdownBackoffMs": 500,
}

_MAX_TOOL_RESULT_CHARS = 4_000
_DATA_URL_RE = re.compile(
    r"data:(?P<mime>[a-zA-Z0-9.+-]+/[a-zA-Z0-9.+-]+);base64,(?P<data>[A-Za-z0-9+/=\s]+)"
)
_BASE64_URI_RE = re.compile(r"base64://(?P<data>[A-Za-z0-9+/=\s]{256,})")


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


class SessionAttemptRunner:
    """Shared tool-loop runner for main/sub agent attempts."""

    def __init__(
        self,
        provider: "LLMProvider",
        tools: "ToolRegistry",
        policy: "ToolPolicyEngine",
        hooks: "HookRunner",
        checkpoint_drain=None,
        max_iterations: int = 100,
        thinking_budget_tokens: int | None = None,
        runtime_execution: dict[str, Any] | None = None,
        runtime_loop_guard: dict[str, Any] | None = None,
    ) -> None:
        self._provider = provider
        self._tools = tools
        self._policy = policy
        self._hooks = hooks
        self._checkpoint_drain = checkpoint_drain
        self._max_iterations = max_iterations
        self._thinking_budget_tokens = thinking_budget_tokens
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

    async def run(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        thread_id: str = "",
        channel: str | None = None,
        chat_id: str | None = None,
        is_subagent: bool = False,
        steer_queue: asyncio.Queue | None = None,
    ) -> AttemptResult:
        msgs = list(messages)
        final_content: str | None = None
        tools_used: list[str] = []
        recent_fingerprints: list[str] = []

        budget = ExecutionBudget(self._execution_cfg)
        trace = RunTrace(session_id=thread_id, is_subagent=is_subagent)

        while True:
            can_start, reason = budget.check_turn_budget()
            if not can_start:
                trace.stop_reason = reason
                trace.add("budget_exhausted", reason=reason, snapshot=budget.snapshot())
                # 子体预算耗尽时，用已有上下文做一次汇总而非直接返回错误
                if is_subagent:
                    try:
                        msgs.append({
                            "role": "user",
                            "content": (
                                "[系统提示] 执行预算已耗尽，无法继续工具调用。"
                                "请根据你到目前为止已收集到的所有信息，"
                                "立即给出一份尽可能完整的汇总结果。"
                                "如有信息缺口，在结尾注明哪些内容未能收集到。"
                                "不要提及预算或系统限制，直接输出内容。"
                            ),
                        })
                        summary_response = await self._provider.chat(
                            messages=msgs,
                            model=model,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            tools=[],
                        )
                        final_content = summary_response.content or ""
                    except Exception as exc:
                        logger.warning(f"[session_attempt] 子体预算耗尽汇总失败: {exc}")
                        final_content = None
                if not final_content:
                    final_content = (
                        f"[预算耗尽] 已完成 {budget.tool_calls_used} 次工具调用，"
                        "但未能在预算内完成全部搜集。请参考其他子体的结果。"
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
                    msgs.append({"role": "user", "content": f"[引导消息] {steer_msg}"})
                    trace.add("steer_injected", message=str(steer_msg)[:200])

            model_override = await self._hooks.run_before_model_resolve(
                HookBeforeModelResolveEvent(
                    current_query="",
                    session_id=thread_id,
                    default_model=model,
                    channel=channel,
                    chat_id=chat_id,
                )
            )
            effective_model = model_override or model
            if self._checkpoint_drain is not None:
                drained_messages = self._checkpoint_drain(
                    thread_id=thread_id,
                    is_subagent=is_subagent,
                )
                if drained_messages:
                    msgs.extend(drained_messages)

            response = await self._provider.chat(
                messages=msgs,
                tools=self._tools.get_definitions(),
                model=effective_model,
                temperature=temperature,
                max_tokens=max_tokens,
                thinking_budget_tokens=self._thinking_budget_tokens,
            )

            if not response.has_tool_calls:
                final_content = response.content
                trace.stop_reason = "model_completed"
                trace.add("model_completed", finish_reason=response.finish_reason)
                break

            fp = _tool_fingerprint(response.tool_calls)
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
                    tool_call_dicts = _make_tool_call_dicts(response.tool_calls)
                    msgs = _add_assistant_msg(msgs, response.content, tool_call_dicts, response.reasoning_content)
                    for tc in response.tool_calls:
                        msgs = _add_tool_result(msgs, tc.id, tc.name, "[工具调用被跳过：检测到重复循环]")
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

            tool_calls = list(response.tool_calls)
            admitted = budget.admit_tool_calls(len(tool_calls))
            if admitted <= 0:
                trace.stop_reason = "max_tool_calls_exhausted"
                trace.add("budget_exhausted", reason="max_tool_calls_exhausted", snapshot=budget.snapshot())
                if is_subagent:
                    try:
                        msgs.append({
                            "role": "user",
                            "content": (
                                "[系统提示] 执行预算已耗尽，无法继续工具调用。"
                                "请根据你到目前为止已收集到的所有信息，"
                                "立即给出一份尽可能完整的汇总结果。"
                                "如有信息缺口，在结尾注明哪些内容未能收集到。"
                                "不要提及预算或系统限制，直接输出内容。"
                            ),
                        })
                        summary_response = await self._provider.chat(
                            messages=msgs,
                            model=model,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            tools=[],
                        )
                        final_content = summary_response.content or ""
                    except Exception as exc:
                        logger.warning(f"[session_attempt] 子体预算耗尽汇总失败: {exc}")
                        final_content = None
                if not final_content:
                    final_content = (
                        f"[预算耗尽] 已完成 {budget.tool_calls_used} 次工具调用，"
                        "但未能在预算内完成全部搜集。请参考其他子体的结果。"
                    )
                break
            if admitted < len(tool_calls):
                trace.add("tool_calls_truncated", requested=len(tool_calls), admitted=admitted)
                tool_calls = tool_calls[:admitted]

            tool_call_dicts = _make_tool_call_dicts(tool_calls)
            msgs = _add_assistant_msg(msgs, response.content, tool_call_dicts, response.reasoning_content)
            for tc in tool_calls:
                tools_used.append(tc.name)

            semaphore = asyncio.Semaphore(self._execution_cfg.tool_concurrency)
            tool_timeout_s = self._execution_cfg.tool_timeout_ms / 1000

            async def _exec(tc: Any) -> tuple[Any, str, dict[str, Any]]:
                async with semaphore:
                    args_str = _safe_json(tc.arguments)
                    logger.info(f"[attempt] tool={tc.name} args={args_str[:200]}")
                    started_at = time.perf_counter()
                    tool_meta = self._tools.get_metadata(tc.name)
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

                    before_result = await self._hooks.run_before_tool_call(
                        HookBeforeToolCallEvent(
                            tool_name=tc.name,
                            params=effective_args,
                            session_id=thread_id,
                            channel=channel,
                            chat_id=chat_id,
                        )
                    )
                    if before_result.block:
                        reason = before_result.block_reason or "插件阻止了此工具调用"
                        duration_ms = int((time.perf_counter() - started_at) * 1000)
                        self._obs.emit(
                            level="warn",
                            kind="event",
                            subsystem="runtime/tools",
                            message="tool_call_hook_blocked",
                            attrs={
                                "toolName": tc.name,
                                "toolCallId": getattr(tc, "id", None),
                                "toolGroup": tool_group,
                                "status": "hook_blocked",
                                "durationMs": duration_ms,
                                "reason": reason,
                            },
                            session_key=thread_id,
                            channel=channel,
                        )
                        return tc, f"[工具调用被拦截：{reason}]", {
                            "status": "hook_blocked",
                            "errorKind": "hook_blocked",
                            "durationMs": duration_ms,
                        }
                    if before_result.params is not None:
                        effective_args = before_result.params

                    async def _run_tool() -> str:
                        try:
                            result = await self._tools.execute(tc.name, effective_args)
                        except Exception as exc:  # noqa: BLE001
                            result = f"工具执行出错：{exc}"
                        asyncio.create_task(
                            self._hooks.run_after_tool_call(
                                HookAfterToolCallEvent(
                                    tool_name=tc.name,
                                    params=effective_args,
                                    result=result,
                                    session_id=thread_id,
                                    channel=channel,
                                    chat_id=chat_id,
                                )
                            )
                        )
                        return str(result)

                    status = "success"
                    error_kind = ""
                    try:
                        result_text = await asyncio.wait_for(_run_tool(), timeout=tool_timeout_s)
                    except asyncio.TimeoutError:
                        status = "timeout"
                        error_kind = "timeout"
                        result_text = f"工具执行超时：{self._execution_cfg.tool_timeout_ms}ms"
                    else:
                        status, error_kind = _classify_tool_result(result_text)

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

                    return tc, result_text, {
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
                compact_result = _compact_tool_result(tc.name, result)
                msgs = _add_tool_result(msgs, tc.id, tc.name, compact_result)
                if meta.get("status") != "success":
                    msgs[-1] = {
                        **msgs[-1],
                        "error_kind": meta.get("errorKind") or None,
                        "duration_ms": meta.get("durationMs"),
                    }

            if self._execution_cfg.tool_failure_policy == "fail_fast" and failed_count > 0:
                final_content = f"任务中止：工具批次失败（{failed_count}/{len(results)}）。"
                trace.stop_reason = "tool_batch_failed"
                trace.add("tool_batch_failed", failed=failed_count, total=len(results))
                break

        return AttemptResult(
            final_content=final_content,
            tools_used=tools_used,
            messages=msgs,
            trace=trace.to_dict(),
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
    result: str,
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


def _compact_tool_result(tool_name: str, result_text: str) -> str:
    text = str(result_text or "")
    text = _replace_embedded_binary(text)
    if len(text) <= _MAX_TOOL_RESULT_CHARS:
        return text
    head = text[:2500]
    tail = text[-1000:]
    return (
        f"{head}\n\n[tool_result_truncated tool={tool_name} "
        f"omitted_chars={len(text) - len(head) - len(tail)} total_chars={len(text)}]\n\n{tail}"
    )


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
