"""Session repository helpers."""

from __future__ import annotations

from auraeve.domain.sessions.models import SessionRecord


class SessionRepository:
    def __init__(self) -> None:
        self._items: dict[str, SessionRecord] = {}
        self._key_index: dict[str, str] = {}

    def save(self, session: SessionRecord) -> None:
        self._items[session.session_id] = session
        self._key_index[session.session_key] = session.session_id

    def get(self, session_id: str) -> SessionRecord | None:
        return self._items.get(session_id)

    def get_by_key(self, session_key: str) -> SessionRecord | None:
        session_id = self._key_index.get(session_key)
        if session_id is None:
            return None
        return self._items.get(session_id)

    def list(self) -> list[SessionRecord]:
        return list(self._items.values())
