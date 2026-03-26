from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from auraeve.session.manager import SessionManager
from auraeve.webui.chat_service import ChatService, RunState
from auraeve.webui.server import WebUIServer


def test_legacy_webui_chat_is_not_marked_as_dev_runtime() -> None:
    item = RunState(run_id="r1", session_key="chat:1", idempotency_key="i1")

    assert not item.session_key.startswith("dev:")


def test_chat_service_rejects_dev_session_keys(tmp_path) -> None:
    service = ChatService(SessionManager(tmp_path), bus=MagicMock())

    with pytest.raises(ValueError):
        service.get_history("dev:main:repo:thread")


def test_webui_chat_api_rejects_dev_session_keys(tmp_path) -> None:
    server = WebUIServer(
        chat_service=ChatService(SessionManager(tmp_path), bus=MagicMock()),
        config_service=MagicMock(),
        token="secret",
    )
    client = TestClient(server._app)

    resp = client.get(
        "/api/webui/chat/history",
        params={"sessionKey": "dev:main:repo:thread"},
        headers={"X-WEBUI-TOKEN": "secret"},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "dev sessions must use the dedicated ACP/dev session APIs"
