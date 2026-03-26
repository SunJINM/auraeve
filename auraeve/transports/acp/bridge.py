"""Minimal ACP bridge scaffold."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from auraeve.domain.sessions.models import SessionRecord
from auraeve.services.session_service import SessionService

from .mapper import build_dev_session_key


class ACPBridge:
    def __init__(self, session_service: SessionService | None = None) -> None:
        # Production wiring should inject a long-lived SessionService.
        self._sessions = session_service or SessionService()

    def get_or_create_session(self, agent_id: str, workspace_id: str, thread_id: str) -> SessionRecord:
        session_key = build_dev_session_key(agent_id, workspace_id, thread_id)
        existing = self._sessions.get_session_by_key(session_key)
        if existing is not None:
            return existing

        session = SessionRecord(
            session_id=self._build_session_id(agent_id, workspace_id, thread_id),
            session_key=session_key,
            session_type="dev_acp",
            runtime_type="acp",
            agent_id=agent_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            state="idle",
        )
        return self._sessions.create_session(session)

    def _build_session_id(self, agent_id: str, workspace_id: str, thread_id: str) -> str:
        source = "\x1f".join((agent_id, workspace_id, thread_id))
        return f"dev-session:{uuid5(NAMESPACE_URL, source)}"
