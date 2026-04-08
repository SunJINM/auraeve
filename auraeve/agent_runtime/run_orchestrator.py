from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger

from auraeve.observability import get_observability
from auraeve.providers.base import (
    AuthError,
    BillingError,
    ContextOverflowError,
    LLMCallError,
    OverloadError,
    ProviderAPIError,
    RateLimitError,
)

if TYPE_CHECKING:
    from auraeve.providers.base import LLMProvider
    from .session_attempt import SessionAttemptRunner, AttemptResult


_RATE_LIMIT_BACKOFF = [5, 10, 20, 40, 60, 60, 60, 60]
_OVERLOAD_BACKOFF = [3, 8, 15, 30, 60, 60, 60, 60]
_SUB_RATE_LIMIT_BACKOFF = [5, 10, 20, 40, 60]
_SUB_OVERLOAD_BACKOFF = [3, 8, 15, 30, 60]


@dataclass
class OrchestratorResult:
    final_content: str | None
    tools_used: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    error_class: str | None = None
    recovery_actions: list[str] = field(default_factory=list)
    trace: dict[str, Any] | None = None


class RunOrchestrator:
    """Unified run orchestrator with integrated recovery strategy."""

    def __init__(
        self,
        runner: "SessionAttemptRunner",
        provider: "LLMProvider",
        max_retries: int = 8,
        is_subagent: bool = False,
    ) -> None:
        self._runner = runner
        self._provider = provider
        self._max_retries = max_retries
        self._is_subagent = is_subagent
        self._rate_backoff = _SUB_RATE_LIMIT_BACKOFF if is_subagent else _RATE_LIMIT_BACKOFF
        self._overload_backoff = _SUB_OVERLOAD_BACKOFF if is_subagent else _OVERLOAD_BACKOFF
        self._obs = get_observability()

    async def run(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        thread_id: str,
        tools=None,
        channel: str | None = None,
        chat_id: str | None = None,
        steer_queue: asyncio.Queue | None = None,
    ) -> OrchestratorResult:
        current_messages = list(messages)
        compaction_attempted = False
        recovery_actions: list[str] = []

        for attempt in range(1, self._max_retries + 1):
            try:
                self._obs.emit(
                    level="debug",
                    kind="trace",
                    subsystem="runtime/orchestrator",
                    message="attempt_started",
                    attrs={"attempt": attempt, "threadId": thread_id, "channel": channel},
                    session_key=thread_id,
                    channel=channel,
                )
                result: AttemptResult = await self._runner.run(
                    messages=current_messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    thread_id=thread_id,
                    channel=channel,
                    chat_id=chat_id,
                    is_subagent=self._is_subagent,
                    steer_queue=steer_queue,
                )
                return OrchestratorResult(
                    final_content=result.final_content,
                    tools_used=result.tools_used,
                    messages=result.messages,
                    recovery_actions=recovery_actions,
                    trace=result.trace,
                )
            except RateLimitError as exc:
                if attempt >= self._max_retries:
                    return OrchestratorResult(
                        final_content="请求频率超过限制，请稍后重试。",
                        error_class="RateLimitError",
                        recovery_actions=recovery_actions,
                    )
                backoff = self._rate_backoff[min(attempt - 1, len(self._rate_backoff) - 1)]
                recovery_actions.append(f"RateLimit backoff={backoff}s attempt={attempt}")
                self._obs.emit(
                    level="warn",
                    kind="trace",
                    subsystem="runtime/orchestrator",
                    message="rate_limit_backoff",
                    attrs={"attempt": attempt, "backoffS": backoff, "error": str(exc)},
                    session_key=thread_id,
                    channel=channel,
                )
                logger.warning(f"[orchestrator] rate limit, retry in {backoff}s: {exc}")
                await asyncio.sleep(backoff)
            except OverloadError as exc:
                if attempt >= self._max_retries:
                    return OrchestratorResult(
                        final_content="模型当前过载，请稍后重试。",
                        error_class="OverloadError",
                        recovery_actions=recovery_actions,
                    )
                backoff = self._overload_backoff[min(attempt - 1, len(self._overload_backoff) - 1)]
                recovery_actions.append(f"Overload backoff={backoff}s attempt={attempt}")
                self._obs.emit(
                    level="warn",
                    kind="trace",
                    subsystem="runtime/orchestrator",
                    message="overload_backoff",
                    attrs={"attempt": attempt, "backoffS": backoff, "error": str(exc)},
                    session_key=thread_id,
                    channel=channel,
                )
                logger.warning(f"[orchestrator] overload, retry in {backoff}s: {exc}")
                await asyncio.sleep(backoff)
            except ProviderAPIError as exc:
                if attempt >= self._max_retries:
                    return OrchestratorResult(
                        final_content=f"上游服务不可用，请稍后重试（{exc}）。",
                        error_class="ProviderAPIError",
                        recovery_actions=recovery_actions,
                    )
                recovery_actions.append(f"ProviderAPIError backoff=5s attempt={attempt}")
                await asyncio.sleep(5)
            except ContextOverflowError as exc:
                if compaction_attempted:
                    return OrchestratorResult(
                        final_content="上下文过长，无法继续处理，请尝试 /new。",
                        error_class="ContextOverflowError",
                        recovery_actions=recovery_actions,
                    )
                compaction_attempted = True
                recovery_actions.append("ContextOverflow compact_and_retry")
                self._obs.emit(
                    level="warn",
                    kind="trace",
                    subsystem="runtime/orchestrator",
                    message="context_overflow_compact",
                    attrs={"attempt": attempt, "error": str(exc)},
                    session_key=thread_id,
                    channel=channel,
                )
                compacted = await self._compact_messages(current_messages)
                if compacted:
                    current_messages = compacted
                    logger.info(f"[orchestrator] compacted messages, retrying: {exc}")
                    continue
                return OrchestratorResult(
                    final_content="上下文过长，无法继续处理，请尝试 /new。",
                    error_class="ContextOverflowError",
                    recovery_actions=recovery_actions,
                )
            except AuthError:
                return OrchestratorResult(
                    final_content="LLM 认证失败，请检查 API Key。",
                    error_class="AuthError",
                    recovery_actions=recovery_actions,
                )
            except BillingError:
                return OrchestratorResult(
                    final_content="API 配额已耗尽，请检查账户余额。",
                    error_class="BillingError",
                    recovery_actions=recovery_actions,
                )
            except LLMCallError as exc:
                if attempt >= self._max_retries:
                    return OrchestratorResult(
                        final_content=f"调用失败，请稍后重试（{exc}）。",
                        error_class=type(exc).__name__,
                        recovery_actions=recovery_actions,
                    )
                recovery_actions.append(f"LLMCallError backoff=5s attempt={attempt}")
                await asyncio.sleep(5)

        return OrchestratorResult(
            final_content="已达到最大重试次数，请稍后重试。",
            error_class="MaxRetriesExceeded",
            recovery_actions=recovery_actions,
        )

    async def _compact_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        try:
            from auraeve.agent.engines.vector.compaction import compact_messages

            system_msgs = [m for m in messages if m.get("role") == "system"]
            history_msgs = [m for m in messages if m.get("role") != "system"]
            if not history_msgs:
                return None
            result = await compact_messages(history_msgs, 80_000, self._provider)
            if result.compacted and result.compacted_messages:
                return system_msgs + result.compacted_messages
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[orchestrator] compaction failed: {exc}")
        return None
