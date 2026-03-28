"""Lightweight event storage for run transcripts, one file per session."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from loguru import logger

from auraeve.domain.runs.models import RunEvent


class RunEventStore:
    def __init__(self, base_dir: Path | str) -> None:
        self._base = Path(base_dir)

    def _session_path(self, session_id: str) -> Path:
        return self._base / f"{session_id}.jsonl"

    def append(self, event: RunEvent) -> None:
        path = self._session_path(event.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def list_for_session(self, session_id: str) -> list[RunEvent]:
        path = self._session_path(session_id)
        if not path.exists():
            return []
        items: list[RunEvent] = []
        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                    items.append(RunEvent(**data))
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    logger.warning(
                        "skip malformed run event line",
                        path=str(path),
                        line_no=line_no,
                        error=str(exc),
                    )
        return items
