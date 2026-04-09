from __future__ import annotations

import base64
import os
import time
import uuid
from pathlib import Path

import httpx

from auraeve.stt.audio_normalize import normalize_for_bytedance_flash_upload
from auraeve.stt.providers.base import STTProvider
from auraeve.stt.types import AuthError, PermanentError, RateLimitError, STTRequest, STTResult, TransientError


class ByteDanceFlashSTTProvider(STTProvider):
    async def transcribe(self, request: STTRequest) -> STTResult:
        api_key = (self.profile.api_key or "").strip()
        if not api_key:
            raise AuthError("bytedance-flash provider requires apiKey")

        started = time.perf_counter()
        endpoint = (self.profile.api_base or "https://openspeech.bytedance.com").rstrip("/")
        url = f"{endpoint}/api/v3/auc/bigmodel/recognize/flash"
        resource_id = str(self.profile.options.get("resourceId") or "volc.bigasr.auc_turbo").strip()
        uid = str(self.profile.options.get("uid") or api_key).strip()
        model_name = (self.profile.model or "bigmodel").strip() or "bigmodel"

        headers = {
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Sequence": "-1",
        }
        payload = {
            "user": {"uid": uid},
            "audio": await self._build_audio_payload(request),
            "request": {"model_name": model_name},
        }

        try:
            async with httpx.AsyncClient(timeout=max(1, self.profile.timeout_ms) / 1000) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = getattr(exc.response, "status_code", 0)
            if status_code in {401, 403}:
                raise AuthError(str(exc)) from exc
            if status_code == 429:
                raise RateLimitError(str(exc)) from exc
            if status_code in {502, 503, 504}:
                raise TransientError(str(exc)) from exc
            raise PermanentError(str(exc)) from exc
        except httpx.TimeoutException as exc:
            raise TransientError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise TransientError(str(exc)) from exc

        api_status = str(response.headers.get("X-Api-Status-Code") or "").strip()
        api_message = str(response.headers.get("X-Api-Message") or "").strip()
        if api_status and api_status != "20000000":
            message = api_message or f"bytedance flash asr failed with code {api_status}"
            if api_status == "55000031" or api_status.startswith("55"):
                raise TransientError(message)
            raise PermanentError(message)

        body = response.json()
        result = body.get("result") if isinstance(body, dict) else {}
        if not isinstance(result, dict):
            raise PermanentError("invalid bytedance flash asr response")

        text = str(result.get("text") or "").strip()
        utterances = result.get("utterances")
        segments: list[dict[str, object]] = []
        if isinstance(utterances, list):
            for item in utterances:
                if not isinstance(item, dict):
                    continue
                segment_text = str(item.get("text") or "").strip()
                segments.append(
                    {
                        "text": segment_text,
                        "startTime": item.get("start_time"),
                        "endTime": item.get("end_time"),
                    }
                )
            if not text:
                text = "\n".join(
                    segment["text"]
                    for segment in segments
                    if isinstance(segment.get("text"), str) and segment["text"]
                )

        return STTResult(
            ok=bool(text),
            text=text or None,
            language=request.language or None,
            provider=self.provider_id,
            latency_ms=int((time.perf_counter() - started) * 1000),
            segments=segments,
            error="" if text else "empty transcription",
        )

    async def _build_audio_payload(self, request: STTRequest) -> dict[str, str]:
        audio_url = str(request.audio_url or "").strip()
        if audio_url:
            return {"url": audio_url}
        normalized_path: str | None = None
        should_cleanup = False
        try:
            normalized_path, should_cleanup, _fmt = await normalize_for_bytedance_flash_upload(str(request.input_path))
            raw = Path(normalized_path).read_bytes()
        except OSError as exc:
            raise PermanentError(f"failed to read audio file: {exc}") from exc
        finally:
            if should_cleanup and normalized_path:
                try:
                    os.unlink(normalized_path)
                except OSError:
                    pass
        if not raw:
            raise PermanentError("audio file is empty")
        return {"data": base64.b64encode(raw).decode("utf-8")}
