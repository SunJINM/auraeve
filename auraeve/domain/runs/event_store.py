"""Lightweight event storage for run transcripts."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from loguru import logger

from auraeve.domain.runs.models import RunEvent


class RunEventStore:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def append(self, event: RunEvent) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def list_for_session(self, session_id: str) -> list[RunEvent]:
        if not self._path.exists():
            return []
        items: list[RunEvent] = []
        with self._path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                    if data.get("session_id") == session_id:
                        items.append(RunEvent(**data))
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    logger.warning(
                        "skip malformed run event line",
                        path=str(self._path),
                        line_no=line_no,
                        error=str(exc),
                    )
        return items
