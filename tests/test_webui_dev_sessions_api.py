from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from auraeve.domain.sessions.models import SessionRecord
from auraeve.services.session_service import SessionService
from auraeve.webui.dev_session_service import DevSessionService
from auraeve.webui.server import WebUIServer


def test_dev_sessions_api_lists_only_dev_sessions_and_reports_total() -> None:
    session_service = SessionService()
    session_service.create_session(
        SessionRecord(
            session_id="dev-1",
            session_key="dev:main:ws1:thread-a",
            session_type="dev_acp",
            runtime_type="acp",
            agent_id="main",
            workspace_id="ws1",
            thread_id="thread-a",
            state="idle",
        )
    )
    session_service.create_session(
        SessionRecord(
            session_id="dev-2",
            session_key="dev:main:ws1:thread-b",
            session_type="dev_acp",
            runtime_type="acp",
            agent_id="main",
            workspace_id="ws1",
            thread_id="thread-b",
            state="idle",
        )
    )
    session_service.create_session(
        SessionRecord(
            session_id="dev-3",
            session_key="dev:main:ws1:thread-c",
            session_type="dev_acp",
            runtime_type="acp",
            agent_id="main",
            workspace_id="ws1",
            thread_id="thread-c",
            state="busy",
        )
    )
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
    assert payload["total"] == 3
    assert len(payload["sessions"]) == 2
    assert payload["sessions"][0]["sessionKey"] == "dev:main:ws1:thread-a"
    assert payload["sessions"][0]["sessionType"] == "dev_acp"


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
