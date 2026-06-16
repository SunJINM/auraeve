from __future__ import annotations

import base64

import pytest

from auraeve.agent.tools.image_generation import ImageGenerationTool


@pytest.mark.asyncio
async def test_generate_image_returns_resource_ref_not_webui_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURAEVE_STATE_DIR", str(tmp_path))

    tool = ImageGenerationTool(api_key="test", api_base="https://example.test")
    setattr(tool, "_current_tool_call_id", "call_img")

    async def fake_generate(prompt: str, size: str) -> list[str]:
        return [base64.b64encode(b"fake image").decode()]

    monkeypatch.setattr(tool, "_generate", fake_generate)

    result = await tool.execute(prompt="多个太阳", mode="generate")

    assert "media://" in str(result.content)
    assert "/api/webui/" not in str(result.content)
    assert result.data["image_refs"][0]["ref"].startswith("media://")
    assert result.data["image_refs"][0]["url"].startswith("/api/webui/resources/")
    assert result.data["image_refs"][0]["toolCallId"] == "call_img"


@pytest.mark.asyncio
async def test_generate_image_accepts_custom_gpt_image_2_size(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURAEVE_STATE_DIR", str(tmp_path))

    tool = ImageGenerationTool(api_key="test", api_base="https://example.test")
    captured: dict[str, str] = {}

    async def fake_generate(prompt: str, size: str) -> list[str]:
        captured["size"] = size
        return [base64.b64encode(b"fake image").decode()]

    monkeypatch.setattr(tool, "_generate", fake_generate)

    result = await tool.execute(prompt="宽屏城市", mode="generate", size="1536x864")

    assert captured["size"] == "1536x864"
    assert result.data["image_refs"][0]["size"] == "1536x864"


@pytest.mark.asyncio
async def test_generate_image_keeps_non_16_multiple_size(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURAEVE_STATE_DIR", str(tmp_path))

    tool = ImageGenerationTool(api_key="test", api_base="https://example.test")
    captured: dict[str, str] = {}

    async def fake_generate(prompt: str, size: str) -> list[str]:
        captured["size"] = size
        return [base64.b64encode(b"fake image").decode()]

    monkeypatch.setattr(tool, "_generate", fake_generate)

    result = await tool.execute(prompt="方图", mode="generate", size="1000x1000")

    assert captured["size"] == "1000x1000"
    assert result.data["image_refs"][0]["size"] == "1000x1000"
