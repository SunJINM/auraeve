import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect

from auraeve.transports.acp.channel import ACPChannel, ACPChannelConfig
from auraeve.webui.server import WebUIServer
from auraeve.services.session_service import SessionService


def _build_server(token: str = "secret") -> WebUIServer:
    session_service = SessionService()
    bus = MagicMock()
    bus.subscribe_outbound = MagicMock()
    bus.unsubscribe_outbound = MagicMock()
    bus.publish_inbound = AsyncMock()
    acp_channel = ACPChannel(
        config=ACPChannelConfig(),
        bus=bus,
        session_service=session_service,
        token=token,
        agent_id="main",
        workspace_id="ws",
    )
    return WebUIServer(
        chat_service=MagicMock(),
        config_service=MagicMock(),
        token=token,
        acp_channel=acp_channel,
    )


def test_acp_websocket_rejects_missing_token() -> None:
    server = _build_server()
    client = TestClient(server._app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/acp"):
            pass


def test_acp_websocket_rejects_wrong_token() -> None:
    server = _build_server()
    client = TestClient(server._app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/acp?token=wrong"):
            pass


def test_acp_websocket_accepts_correct_token() -> None:
    server = _build_server()
    client = TestClient(server._app)
    with client.websocket_connect("/acp?token=secret") as ws:
        ws.send_text(json.dumps({
            "jsonrpc": "2.0", "id": "1", "method": "initialize",
            "params": {"protocolVersion": "1.0", "agentId": "main"},
        }))
        resp = json.loads(ws.receive_text())
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == "1"
        assert resp["result"]["protocolVersion"] == "1.0"


def test_acp_new_session_and_list_sessions() -> None:
    server = _build_server()
    client = TestClient(server._app)
    with client.websocket_connect("/acp?token=secret") as ws:
        ws.send_text(json.dumps({
            "jsonrpc": "2.0", "id": "2", "method": "newSession",
            "params": {"agentId": "main", "cwd": "/repo"},
        }))
        resp = json.loads(ws.receive_text())
        assert resp["result"]["session"]["state"] == "idle"
        session_id = resp["result"]["session"]["sessionId"]

        ws.send_text(json.dumps({
            "jsonrpc": "2.0", "id": "3", "method": "unstable_listSessions", "params": {},
        }))
        resp2 = json.loads(ws.receive_text())
        assert resp2["result"]["total"] == 1
        assert resp2["result"]["sessions"][0]["sessionId"] == session_id
