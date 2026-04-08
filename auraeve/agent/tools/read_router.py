from __future__ import annotations

from pathlib import Path
from typing import Any

from auraeve.agent.tools import file_read_support
from auraeve.agent.tools.base import ToolExecutionResult
from auraeve.llm.model_registry import ModelRegistry


class ReadRouter:
    def __init__(
        self,
        *,
        model_registry: ModelRegistry,
        image_to_text_service,
        asr_runtime,
        read_routing: dict[str, Any],
    ) -> None:
        self._model_registry = model_registry
        self._image_to_text_service = image_to_text_service
        self._asr_runtime = asr_runtime
        self._read_routing = read_routing

    async def read_file(
        self,
        file_path: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
        pages: str | None = None,
    ) -> ToolExecutionResult:
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix in file_read_support.IMAGE_SUFFIXES:
            return await self._read_image(path)
        if suffix == ".pdf":
            return await file_read_support.read_pdf_file(str(path), pages)
        if suffix == ".ipynb":
            return file_read_support.read_notebook_file(str(path))
        if suffix in file_read_support.AUDIO_SUFFIXES:
            return await self._read_audio(path)
        return file_read_support.read_text_file(path, offset, limit)

    async def _read_image(self, path: Path) -> ToolExecutionResult:
        primary = self._model_registry.primary()
        if primary.capabilities.image_input:
            return await file_read_support.read_image_file(str(path))

        if not bool(self._read_routing.get("imageFallbackEnabled", True)):
            return ToolExecutionResult(
                content="Error: primary model does not support image input",
                data={"type": "error", "filePath": str(path)},
            )

        vision_model = self._model_registry.first_enabled_with_capability("imageInput")
        if vision_model is None:
            return ToolExecutionResult(
                content="Error: no enabled model with image input capability is configured",
                data={"type": "error", "filePath": str(path)},
            )

        text = await self._image_to_text_service.describe(
            image_path=str(path),
            user_prompt=str(self._read_routing.get("imageToTextPrompt") or ""),
            model_card=vision_model,
        )
        return ToolExecutionResult(
            content=text,
            data={"type": "image_text", "filePath": str(path), "modelId": vision_model.id},
        )

    async def _read_audio(self, path: Path) -> ToolExecutionResult:
        if self._asr_runtime is None:
            return ToolExecutionResult(
                content="Error: ASR runtime is not configured",
                data={"type": "error", "filePath": str(path)},
            )
        text = await self._asr_runtime.transcribe_file(str(path), channel="read")
        return ToolExecutionResult(
            content=text or "",
            data={"type": "audio_text", "filePath": str(path)},
        )
