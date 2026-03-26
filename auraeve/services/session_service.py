"""Session service helpers."""

from __future__ import annotations

from auraeve.domain.sessions.models import SessionRecord
from auraeve.domain.sessions.repository import SessionRepository


class SessionService:
    def __init__(self, repository: SessionRepository | None = None) -> None:
        self._repository = repository or SessionRepository()

    def create_session(self, session: SessionRecord) -> SessionRecord:
        self._repository.save(session)
        return session

    def get_session(self, session_id: str) -> SessionRecord | None:
        return self._repository.get(session_id)

    def get_session_by_key(self, session_key: str) -> SessionRecord | None:
        return self._repository.get_by_key(session_key)

    def list_sessions(self) -> list[SessionRecord]:
        return self._repository.list()
