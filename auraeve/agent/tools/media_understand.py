from __future__ import annotations

from copy import deepcopy
from typing import Any

from auraeve.agent.tools.base import Tool
from auraeve.bus.events import FileAttachment


class MediaUnderstandTool(Tool):
    """Unified media understanding tool."""

    def __init__(self, runtime) -> None:
        self._runtime = runtime
        self._context_content: str = ""
        self._context_media: list[str] = []
        self._context_attachments: list[FileAttachment] = []

    def set_context(
        self,
        *,
        content: str,
        media: list[str] | None,
        attachments: list[FileAttachment] | None,
    ) -> None:
        self._context_content = content or ""
        self._context_media = list(media or [])
        # Keep per-turn context isolated from later runtime mutations.
        self._context_attachments = deepcopy(list(attachments or []))

    @property
    def name(self) -> str:
        return "media_understand"

    @property
    def description(self) -> str:
        return "Preprocess media and attachments into model-friendly text and image blocks."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Current message text"},
                "model": {"type": "string", "description": "Current model name"},
                "media": {
                    "type": "array",
                    "description": "Media paths or URLs",
                    "items": {"type": "string"},
                },
                "attachments": {
                    "type": "array",
                    "description": "Attachment list (filename/url/mime_type/size). Optional: defaults to current message attachments.",
                    "items": {"type": "object"},
                },
            },
            "required": ["model"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        model: str,
        content: str = "",
        media: list[str] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> str:
        normalized_attachments: list[FileAttachment] = []
        if attachments is None:
            normalized_attachments = deepcopy(self._context_attachments)
        else:
            for item in attachments:
                if not isinstance(item, dict):
                    continue
                normalized_attachments.append(
                    FileAttachment(
                        filename=str(item.get("filename") or "file"),
                        url=str(item.get("url") or ""),
                        mime_type=str(item.get("mime_type") or ""),
                        size=int(item.get("size") or 0),
                    )
                )

        result = await self._runtime.preprocess_inbound(
            content=content or self._context_content,
            model=model,
            media=(media if media is not None else self._context_media),
            attachments=normalized_attachments,
        )
        return (
            f"content={result.content}\n"
            f"media={result.media or []}\n"
            f"attachments={len(result.attachments or [])}"
        )
