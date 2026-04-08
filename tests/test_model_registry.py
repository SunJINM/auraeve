from __future__ import annotations

from auraeve.llm.model_registry import ModelRegistry


def _models():
    return [
        {
            "id": "main",
            "label": "Main",
            "enabled": True,
            "isPrimary": True,
            "model": "gpt-5-mini",
            "apiBase": None,
            "apiKey": "k-main",
            "extraHeaders": {},
            "maxTokens": 4096,
            "temperature": 0.2,
            "thinkingBudgetTokens": 0,
            "capabilities": {
                "imageInput": False,
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
            "model": "gpt-4o",
            "apiBase": None,
            "apiKey": "k-vision",
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
    ]


def test_model_registry_returns_primary_model() -> None:
    registry = ModelRegistry(_models())
    primary = registry.primary()
    assert primary.id == "main"
    assert primary.model == "gpt-5-mini"


def test_model_registry_finds_first_enabled_model_by_capability() -> None:
    registry = ModelRegistry(_models())
    vision = registry.first_enabled_with_capability("imageInput")
    assert vision is not None
    assert vision.id == "vision"


def test_model_registry_returns_none_when_capability_unavailable() -> None:
    registry = ModelRegistry(_models())
    assert registry.first_enabled_with_capability("audioInput") is None
