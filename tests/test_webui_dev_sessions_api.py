from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from auraeve.domain.sessions.models import SessionRecord
from auraeve.services.session_service import SessionService
from auraeve.webui.dev_session_service import DevSessionService
from auraeve.webui.server import WebUIServer


def _make_dev_session(session_id: str, thread_id: str) -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        session_key=f"dev:main:ws1:{thread_id}",
        session_type="dev_acp",
        runtime_type="acp",
        agent_id="main",
        workspace_id="ws1",
        thread_id=thread_id,
        state="idle",
    )


def test_dev_sessions_api_lists_only_dev_sessions_and_reports_total() -> None:
    session_service = SessionService()
    session_service.create_session(_make_dev_session("dev-1", "thread-a"))
    session_service.create_session(_make_dev_session("dev-2", "thread-b"))
    session_service.create_session(_make_dev_session("dev-3", "thread-c"))
    session_service.create_session(
        SessionRecord(
            session_id="chat-1",
            session_key="webui:chat-1",
            session_type="chat",
            runtime_type="native",
            agent_id="main",
            workspace_id="default",
            thread_id="chat-1",
            state="active",
        )
    )

    server = WebUIServer(
        chat_service=MagicMock(),
        config_service=MagicMock(),
        token="secret",
        dev_session_service=DevSessionService(session_service),
    )
    client = TestClient(server._app)

    resp = client.get(
        "/api/webui/dev/sessions?limit=2",
        headers={"X-WEBUI-TOKEN": "secret"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["total"] == 2
    assert len(payload["sessions"]) == 2


def test_dev_sessions_api_passes_limit_to_service() -> None:
    """API 应将 limit 参数直接传给 service，不应在 server 层二次截断。"""
    dev_svc = MagicMock(spec=DevSessionService)
    dev_svc.list_sessions.return_value = []

    server = WebUIServer(
        chat_service=MagicMock(),
        config_service=MagicMock(),
        token="secret",
        dev_session_service=dev_svc,
    )
    client = TestClient(server._app)

    client.get("/api/webui/dev/sessions?limit=5", headers={"X-WEBUI-TOKEN": "secret"})

    dev_svc.list_sessions.assert_called_once_with(limit=5)


def test_dev_sessions_api_requires_injected_service() -> None:
    server = WebUIServer(
        chat_service=MagicMock(),
        config_service=MagicMock(),
        token="secret",
    )
    client = TestClient(server._app)

    resp = client.get(
        "/api/webui/dev/sessions",
        headers={"X-WEBUI-TOKEN": "secret"},
    )

    assert resp.status_code == 503
    assert resp.json()["detail"] == "dev session api is disabled until dev_session_service is injected"
