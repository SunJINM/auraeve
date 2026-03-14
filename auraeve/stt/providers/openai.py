from __future__ import annotations

import os
import time

from openai import AsyncOpenAI

from auraeve.stt.providers.base import STTProvider
from auraeve.stt.types import AuthError, PermanentError, RateLimitError, STTRequest, STTResult, TransientError


class OpenAISTTProvider(STTProvider):
    def __init__(self, profile):
        super().__init__(profile)
        api_key = profile.api_key or os.environ.get("OPENAI_API_KEY", "")
        self._client = AsyncOpenAI(api_key=api_key, base_url=profile.api_base or None)

    async def transcribe(self, request: STTRequest) -> STTResult:
        started = time.perf_counter()
        try:
            with open(request.input_path, "rb") as f:
                resp = await self._client.audio.transcriptions.create(
                    model=self.profile.model or "gpt-4o-mini-transcribe",
                    file=f,
                    language=(request.language or "zh-CN"),
                )
            text = (getattr(resp, "text", "") or "").strip()
            return STTResult(
                ok=bool(text),
                text=text or None,
                language=request.language or None,
                provider=self.provider_id,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error="" if text else "empty transcription",
            )
        except Exception as exc:
            msg = str(exc).lower()
            if "401" in msg or "403" in msg or "unauthorized" in msg:
                raise AuthError(str(exc)) from exc
            if "429" in msg or "rate" in msg:
                raise RateLimitError(str(exc)) from exc
            if "timeout" in msg or "connection" in msg or "503" in msg or "502" in msg:
                raise TransientError(str(exc)) from exc
            raise PermanentError(str(exc)) from exc

