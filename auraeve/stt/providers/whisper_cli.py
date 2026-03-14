from __future__ import annotations

import asyncio
import os
import shlex
import time

from auraeve.stt.providers.base import STTProvider
from auraeve.stt.types import PermanentError, STTRequest, STTResult, TransientError


class WhisperCLIProvider(STTProvider):
    async def transcribe(self, request: STTRequest) -> STTResult:
        if not self.profile.command:
            raise PermanentError("whisper-cli provider requires command")

        started = time.perf_counter()
        args = self.profile.args_template or ["{{input}}", "--language", "{{language}}"]
        resolved = [
            item.replace("{{input}}", str(request.input_path)).replace("{{language}}", request.language or "zh-CN")
            for item in args
        ]
        cmd = [self.profile.command, *resolved]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise PermanentError(f"command not found: {self.profile.command}") from exc
        except Exception as exc:
            raise TransientError(str(exc)) from exc

        try:
            out, err = await asyncio.wait_for(
                proc.communicate(),
                timeout=max(1, self.profile.timeout_ms) / 1000,
            )
        except asyncio.TimeoutError as exc:
            proc.kill()
            raise TransientError("whisper-cli timeout") from exc

        if proc.returncode != 0:
            tail = err.decode(errors="replace")[-200:]
            raise PermanentError(f"whisper-cli failed: {tail}")

        text = out.decode(errors="replace").strip()
        if not text:
            text = err.decode(errors="replace").strip()
        return STTResult(
            ok=bool(text),
            text=text or None,
            language=request.language or None,
            provider=self.provider_id,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error="" if text else "empty output",
        )

