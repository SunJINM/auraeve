from __future__ import annotations

import asyncio
import time

from auraeve.stt.providers.base import STTProvider
from auraeve.stt.types import PermanentError, STTRequest, STTResult


class FunASRLocalProvider(STTProvider):
    def __init__(self, profile):
        super().__init__(profile)
        self._model = None

    async def _ensure_model(self):
        if self._model is not None:
            return self._model
        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise PermanentError("funasr is not installed") from exc

        model_name = self.profile.model or "paraformer-zh"
        loop = asyncio.get_running_loop()
        self._model = await loop.run_in_executor(
            None,
            lambda: AutoModel(
                model=model_name,
                vad_model="fsmn-vad",
                punc_model="ct-punc",
                disable_update=True,
            ),
        )
        return self._model

    async def transcribe(self, request: STTRequest) -> STTResult:
        started = time.perf_counter()
        model = await self._ensure_model()

        try:
            import numpy as np
            import soundfile as sf
        except ImportError as exc:
            raise PermanentError("funasr-local requires soundfile and numpy") from exc

        loop = asyncio.get_running_loop()
        audio_data, sr = await loop.run_in_executor(
            None,
            lambda: sf.read(str(request.input_path), dtype="float32"),
        )
        if getattr(audio_data, "ndim", 1) > 1:
            audio_data = audio_data.mean(axis=1)
        if sr != 16000:
            ratio = 16000 / sr
            new_len = int(len(audio_data) * ratio)
            audio_data = np.interp(
                np.linspace(0, len(audio_data) - 1, new_len),
                np.arange(len(audio_data)),
                audio_data,
            ).astype(np.float32)

        resp = await loop.run_in_executor(None, lambda: model.generate(input=audio_data))
        text = ""
        if resp and isinstance(resp, list):
            text = str((resp[0] or {}).get("text") or "").strip()

        return STTResult(
            ok=bool(text),
            text=text or None,
            language=request.language or None,
            provider=self.provider_id,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error="" if text else "empty transcription",
        )

