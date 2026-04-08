from __future__ import annotations

from pathlib import Path

from auraeve.agent.tools import file_read_support
from auraeve.llm.model_registry import ModelCard


class ImageToTextService:
    def __init__(self, *, prompt: str) -> None:
        self._prompt = prompt

    async def describe(self, *, image_path: str, user_prompt: str, model_card: ModelCard) -> str:
        from auraeve.providers.openai_provider import OpenAICompatibleProvider

        data_url = file_read_support.encode_image_as_data_url(Path(image_path))
        provider = OpenAICompatibleProvider(
            api_key=model_card.api_key,
            api_base=model_card.api_base,
            default_model=model_card.model,
            extra_headers=model_card.extra_headers,
        )
        response = await provider.chat(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt or self._prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            model=model_card.model,
            max_tokens=min(model_card.max_tokens or 1024, 1024),
            temperature=0.1,
            thinking_budget_tokens=0,
        )
        return (response.content or "").strip()
