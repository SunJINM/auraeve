from __future__ import annotations

from pathlib import Path

import pytest

from auraeve.agent.tools.read_router import ReadRouter
from auraeve.llm.model_registry import ModelRegistry


class _FakeImageToTextService:
    async def describe(self, *, image_path: str, user_prompt: str, model_card) -> str:
        return (
            f"<attachment name=\"{Path(image_path).name}\">\n"
            "summary: chart\n"
            "ocr_text: hello\n"
            "</attachment>"
        )


class _FakeAsrRuntime:
    async def transcribe_file(self, file_path: str, *, channel: str) -> str:
        return "meeting transcript"


def _registry(image_primary: bool) -> ModelRegistry:
    return ModelRegistry([
        {
            "id": "main",
            "label": "Main",
            "enabled": True,
            "isPrimary": True,
            "model": "main-model",
            "apiBase": None,
            "apiKey": "main-key",
            "extraHeaders": {},
            "maxTokens": 4096,
            "temperature": 0.2,
            "thinkingBudgetTokens": 0,
            "capabilities": {
                "imageInput": image_primary,
                "audioInput": False,
                "documentInput": True,
                "toolCalling": True,
                "streaming": True,
            },
        },
        {
            "id": "vision",
            "label": "Vision",
            "enabled": True,
            "isPrimary": False,
            "model": "vision-model",
            "apiBase": None,
            "apiKey": "vision-key",
            "extraHeaders": {},
            "maxTokens": 4096,
            "temperature": 0.1,
            "thinkingBudgetTokens": 0,
            "capabilities": {
                "imageInput": True,
                "audioInput": False,
                "documentInput": True,
                "toolCalling": True,
                "streaming": True,
            },
        },
    ])


@pytest.mark.asyncio
async def test_read_router_uses_native_image_blocks_when_primary_supports_images(tmp_path: Path) -> None:
    target = tmp_path / "demo.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    router = ReadRouter(
        model_registry=_registry(True),
        image_to_text_service=_FakeImageToTextService(),
        asr_runtime=_FakeAsrRuntime(),
        read_routing={"imageFallbackEnabled": True, "failWhenNoImageModel": True, "imageToTextPrompt": "describe"},
    )
    result = await router.read_file(str(target))
    assert result.data["type"] == "image"
    assert result.extra_messages


@pytest.mark.asyncio
async def test_read_router_converts_image_to_text_when_primary_lacks_image_support(tmp_path: Path) -> None:
    target = tmp_path / "demo.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    router = ReadRouter(
        model_registry=_registry(False),
        image_to_text_service=_FakeImageToTextService(),
        asr_runtime=_FakeAsrRuntime(),
        read_routing={"imageFallbackEnabled": True, "failWhenNoImageModel": True, "imageToTextPrompt": "describe"},
    )
    result = await router.read_file(str(target))
    assert result.data["type"] == "image_text"
    assert "summary: chart" in result.content


@pytest.mark.asyncio
async def test_read_router_uses_asr_for_audio_files(tmp_path: Path) -> None:
    target = tmp_path / "voice.mp3"
    target.write_bytes(b"ID3fake")
    router = ReadRouter(
        model_registry=_registry(False),
        image_to_text_service=_FakeImageToTextService(),
        asr_runtime=_FakeAsrRuntime(),
        read_routing={"imageFallbackEnabled": True, "failWhenNoImageModel": True, "imageToTextPrompt": "describe"},
    )
    result = await router.read_file(str(target))
    assert result.data["type"] == "audio_text"
    assert result.content == "meeting transcript"
