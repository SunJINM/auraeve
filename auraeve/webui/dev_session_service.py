"""WebUI helpers for development sessions."""

from __future__ import annotations

from typing import Any

from auraeve.domain.sessions.models import SessionRecord
from auraeve.services.session_service import SessionService


class DevSessionService:
    def __init__(self, session_service: SessionService) -> None:
        self._sessions = session_service

    def list_sessions(self, limit: int | None = 200) -> list[SessionRecord]:
        sessions = [
            session
            for session in self._sessions.list_sessions()
            if session.session_type == "dev_acp"
        ]
        if limit is None:
            return sessions
        if limit <= 0:
            return []
        return sessions[:limit]

    @staticmethod
    def to_dict(session: SessionRecord) -> dict[str, Any]:
        return {
            "sessionId": session.session_id,
            "sessionKey": session.session_key,
            "sessionType": session.session_type,
            "runtimeType": session.runtime_type,
            "agentId": session.agent_id,
            "workspaceId": session.workspace_id,
            "threadId": session.thread_id,
            "state": session.state,
            "metadata": dict(session.metadata),
        }
