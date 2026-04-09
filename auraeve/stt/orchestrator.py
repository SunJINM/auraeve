from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from loguru import logger

from auraeve.stt.audio_normalize import normalize_for_stt
from auraeve.stt.providers.base import STTProvider
from auraeve.stt.types import (
    AuthError,
    PermanentError,
    RateLimitError,
    STTAttempt,
    STTRequest,
    STTResult,
    TransientError,
)


def _error_category(exc: Exception) -> str:
    if isinstance(exc, AuthError):
        return "auth"
    if isinstance(exc, RateLimitError):
        return "rate_limit"
    if isinstance(exc, TransientError):
        return "transient"
    if isinstance(exc, PermanentError):
        return "permanent"
    return "unknown"


class STTOrchestrator:
    def __init__(
        self,
        providers: list[STTProvider],
        *,
        timeout_ms: int,
        retry_count: int,
        failover_enabled: bool,
        max_concurrency: int,
    ) -> None:
        self.providers = providers
        self.timeout_ms = timeout_ms
        self.retry_count = retry_count
        self.failover_enabled = failover_enabled
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def transcribe(self, request: STTRequest) -> STTResult:
        attempts: list[STTAttempt] = []
        if not self.providers:
            return STTResult(ok=False, error="no stt provider enabled", attempts=attempts)

        normalized_path: str | None = None
        should_cleanup = False

        async with self._semaphore:
            if request.audio_url:
                req = STTRequest(
                    input_path=request.input_path,
                    audio_url=request.audio_url,
                    channel=request.channel,
                    language=request.language,
                    provider_profile=request.provider_profile,
                    metadata=request.metadata,
                )
            else:
                normalized_path, should_cleanup, _fmt = await normalize_for_stt(str(request.input_path))
                req = STTRequest(
                    input_path=Path(normalized_path),
                    audio_url="",
                    channel=request.channel,
                    language=request.language,
                    provider_profile=request.provider_profile,
                    metadata=request.metadata,
                )

            try:
                for provider in self.providers:
                    total_try = max(1, self.retry_count + 1)
                    for _ in range(total_try):
                        started = time.perf_counter()
                        try:
                            result = await asyncio.wait_for(
                                provider.transcribe(req),
                                timeout=max(1, provider.profile.timeout_ms or self.timeout_ms) / 1000,
                            )
                            latency = int((time.perf_counter() - started) * 1000)
                            attempts.append(STTAttempt(provider_id=provider.provider_id, ok=result.ok, latency_ms=latency))
                            if result.ok:
                                result.provider = provider.provider_id
                                result.attempts = attempts
                                result.latency_ms = sum(item.latency_ms for item in attempts)
                                return result
                            if not self.failover_enabled:
                                return STTResult(
                                    ok=False,
                                    error=result.error or "provider returned empty result",
                                    provider=provider.provider_id,
                                    attempts=attempts,
                                )
                        except Exception as exc:
                            category = _error_category(exc)
                            latency = int((time.perf_counter() - started) * 1000)
                            attempts.append(
                                STTAttempt(
                                    provider_id=provider.provider_id,
                                    ok=False,
                                    latency_ms=latency,
                                    error=str(exc),
                                    error_category=category,
                                )
                            )
                            if category in {"auth", "permanent"}:
                                break
                            if category == "transient":
                                await asyncio.sleep(0.15)
                    if not self.failover_enabled:
                        break
            finally:
                if should_cleanup and normalized_path:
                    try:
                        os.unlink(normalized_path)
                    except OSError:
                        pass

        message = "all providers failed"
        if attempts:
            last = attempts[-1]
            if last.error:
                message = last.error
        return STTResult(ok=False, error=message, attempts=attempts, latency_ms=sum(item.latency_ms for item in attempts))

