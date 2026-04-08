from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ModelCapabilities:
    image_input: bool
    audio_input: bool
    document_input: bool
    tool_calling: bool
    streaming: bool


@dataclass(slots=True)
class ModelCard:
    id: str
    label: str
    enabled: bool
    is_primary: bool
    model: str
    api_base: str | None
    api_key: str
    extra_headers: dict[str, str]
    max_tokens: int
    temperature: float
    thinking_budget_tokens: int
    capabilities: ModelCapabilities


class ModelRegistry:
    def __init__(self, raw_models: list[dict[str, Any]]) -> None:
        self._models = [self._parse_model(item) for item in raw_models if isinstance(item, dict)]

    def all_enabled(self) -> list[ModelCard]:
        return [item for item in self._models if item.enabled]

    def primary(self) -> ModelCard:
        for item in self._models:
            if item.enabled and item.is_primary:
                return item
        raise ValueError("No enabled primary model configured")

    def first_enabled_with_capability(self, capability: str) -> ModelCard | None:
        for item in self._models:
            if not item.enabled:
                continue
            if self._has_capability(item, capability):
                return item
        return None

    def _has_capability(self, item: ModelCard, capability: str) -> bool:
        mapping = {
            "imageInput": item.capabilities.image_input,
            "audioInput": item.capabilities.audio_input,
            "documentInput": item.capabilities.document_input,
            "toolCalling": item.capabilities.tool_calling,
            "streaming": item.capabilities.streaming,
        }
        return mapping.get(capability, False)

    def _parse_model(self, raw: dict[str, Any]) -> ModelCard:
        caps = raw.get("capabilities") or {}
        api_base_raw = raw.get("apiBase")
        api_base = api_base_raw.strip() if isinstance(api_base_raw, str) and api_base_raw.strip() else None
        return ModelCard(
            id=str(raw.get("id") or ""),
            label=str(raw.get("label") or ""),
            enabled=bool(raw.get("enabled", True)),
            is_primary=bool(raw.get("isPrimary", False)),
            model=str(raw.get("model") or ""),
            api_base=api_base,
            api_key=str(raw.get("apiKey") or ""),
            extra_headers=dict(raw.get("extraHeaders") or {}),
            max_tokens=int(raw.get("maxTokens") or 0),
            temperature=float(raw.get("temperature") or 0.0),
            thinking_budget_tokens=int(raw.get("thinkingBudgetTokens") or 0),
            capabilities=ModelCapabilities(
                image_input=bool(caps.get("imageInput", False)),
                audio_input=bool(caps.get("audioInput", False)),
                document_input=bool(caps.get("documentInput", False)),
                tool_calling=bool(caps.get("toolCalling", False)),
                streaming=bool(caps.get("streaming", False)),
            ),
        )
