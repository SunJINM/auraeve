# tests/test_acp_protocol.py
import json
from auraeve.transports.acp.protocol import (
    JsonRpcRequest, JsonRpcResponse, JsonRpcError,
    JsonRpcNotification,
    InitializeParams, InitializeResult,
    NewSessionParams, NewSessionResult,
    LoadSessionParams, LoadSessionResult,
    PromptParams, PromptResult,
    SessionInfo, AcpCapabilities,
    parse_jsonrpc, JSONRPC_VERSION,
)


def test_jsonrpc_request_serializes() -> None:
    req = JsonRpcRequest(id="1", method="initialize", params={"protocolVersion": "1.0"})
    data = req.to_dict()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == "1"
    assert data["method"] == "initialize"
    assert data["params"]["protocolVersion"] == "1.0"


def test_jsonrpc_response_serializes() -> None:
    resp = JsonRpcResponse(id="1", result={"ok": True})
    data = resp.to_dict()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == "1"
    assert data["result"]["ok"] is True
    assert "error" not in data


def test_jsonrpc_error_serializes() -> None:
    err = JsonRpcError(id="1", code=-32600, message="Invalid Request")
    data = err.to_dict()
    assert data["jsonrpc"] == "2.0"
    assert data["error"]["code"] == -32600
    assert data["error"]["message"] == "Invalid Request"
    assert "result" not in data


def test_jsonrpc_notification_has_no_id() -> None:
    notif = JsonRpcNotification(method="cancel", params={"runId": "r1"})
    data = notif.to_dict()
    assert "id" not in data
    assert data["method"] == "cancel"


def test_parse_jsonrpc_request() -> None:
    raw = json.dumps({"jsonrpc": "2.0", "id": "42", "method": "prompt", "params": {"sessionId": "s1", "blocks": []}})
    msg = parse_jsonrpc(raw)
    assert isinstance(msg, JsonRpcRequest)
    assert msg.method == "prompt"
    assert msg.id == "42"


def test_parse_jsonrpc_notification_no_id() -> None:
    raw = json.dumps({"jsonrpc": "2.0", "method": "cancel", "params": {"runId": "r1"}})
    msg = parse_jsonrpc(raw)
    assert isinstance(msg, JsonRpcNotification)
    assert msg.method == "cancel"


def test_parse_jsonrpc_invalid_returns_error() -> None:
    msg = parse_jsonrpc("not json")
    assert isinstance(msg, JsonRpcError)
    assert msg.code == -32700  # Parse error


def test_initialize_params_defaults() -> None:
    p = InitializeParams(protocolVersion="1.0", agentId="main")
    assert p.capabilities == {}
    assert p.cwd is None


def test_session_info_fields() -> None:
    s = SessionInfo(sessionId="s1", sessionKey="dev:main:ws:t1", state="idle")
    assert s.sessionId == "s1"
    assert s.state == "idle"


def test_prompt_params_blocks() -> None:
    p = PromptParams(
        sessionId="s1",
        runId="r1",
        blocks=[{"type": "text", "text": "hello"}],
    )
    assert len(p.blocks) == 1
    assert p.blocks[0]["text"] == "hello"
