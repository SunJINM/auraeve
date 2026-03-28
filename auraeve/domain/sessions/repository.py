"""Session repository with optional JSONL persistence."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from auraeve.domain.sessions.models import SessionRecord


class SessionRepository:
    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._items: dict[str, SessionRecord] = {}
        self._key_index: dict[str, str] = {}
        if self._path and self._path.exists():
            self._load()

    def _load(self) -> None:
        assert self._path is not None
        for line in self._path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
                record = SessionRecord(**data)
                self._items[record.session_id] = record
                self._key_index[record.session_key] = record.session_id
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

    def save(self, session: SessionRecord) -> None:
        self._items[session.session_id] = session
        self._key_index[session.session_key] = session.session_id
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(session), ensure_ascii=False) + "\n")

    def get(self, session_id: str) -> SessionRecord | None:
        return self._items.get(session_id)

    def get_by_key(self, session_key: str) -> SessionRecord | None:
        session_id = self._key_index.get(session_key)
        if session_id is None:
            return None
        return self._items.get(session_id)

    def list(self) -> list[SessionRecord]:
        return list(self._items.values())
