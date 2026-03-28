import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from auraeve.transports.acp.dispatcher import ACPDispatcher
from auraeve.transports.acp.protocol import (
    JsonRpcRequest, JsonRpcResponse, JsonRpcError, JsonRpcNotification,
)
from auraeve.domain.sessions.models import SessionRecord


def _make_session(session_id: str = "s1") -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        session_key=f"dev:main:ws:{session_id}",
        session_type="dev_acp",
        runtime_type="acp",
        agent_id="main",
        workspace_id="ws",
        thread_id=session_id,
        state="idle",
    )


@pytest.fixture
def dispatcher():
    bus = MagicMock()
    bus.publish_inbound = AsyncMock()
    session_service = MagicMock()
    session_service.list_sessions = MagicMock(return_value=[])
    session_service.get_session = MagicMock(return_value=None)
    session_service.create_session = MagicMock(side_effect=lambda s: s)
    session_service.update_session = MagicMock(side_effect=lambda s: s)
    return ACPDispatcher(bus=bus, session_service=session_service, agent_id="main", workspace_id="ws")


@pytest.mark.asyncio
async def test_initialize_returns_protocol_version(dispatcher) -> None:
    req = JsonRpcRequest(id="1", method="initialize", params={"protocolVersion": "1.0", "agentId": "main"})
    resp = await dispatcher.dispatch(req)
    assert isinstance(resp, JsonRpcResponse)
    assert resp.result["protocolVersion"] == "1.0"
    assert "capabilities" in resp.result


@pytest.mark.asyncio
async def test_new_session_creates_session(dispatcher) -> None:
    req = JsonRpcRequest(id="2", method="newSession", params={"agentId": "main", "cwd": "/repo"})
    resp = await dispatcher.dispatch(req)
    assert isinstance(resp, JsonRpcResponse)
    assert "session" in resp.result
    assert resp.result["session"]["state"] == "idle"


@pytest.mark.asyncio
async def test_load_session_returns_error_when_not_found(dispatcher) -> None:
    dispatcher._session_service.get_session = MagicMock(return_value=None)
    req = JsonRpcRequest(id="3", method="loadSession", params={"sessionId": "nonexistent"})
    resp = await dispatcher.dispatch(req)
    assert isinstance(resp, JsonRpcError)
    assert resp.code == -32001  # Session not found


@pytest.mark.asyncio
async def test_load_session_returns_session_when_found(dispatcher) -> None:
    session = _make_session("s1")
    dispatcher._session_service.get_session = MagicMock(return_value=session)
    req = JsonRpcRequest(id="4", method="loadSession", params={"sessionId": "s1"})
    resp = await dispatcher.dispatch(req)
    assert isinstance(resp, JsonRpcResponse)
    assert resp.result["session"]["sessionId"] == "s1"
    assert resp.result["loaded"] is True


@pytest.mark.asyncio
async def test_prompt_publishes_inbound_message(dispatcher) -> None:
    session = _make_session("s1")
    dispatcher._session_service.get_session = MagicMock(return_value=session)
    req = JsonRpcRequest(
        id="5",
        method="prompt",
        params={"sessionId": "s1", "runId": "r1", "blocks": [{"type": "text", "text": "hello"}]},
    )
    resp = await dispatcher.dispatch(req)
    assert isinstance(resp, JsonRpcResponse)
    assert resp.result["runId"] == "r1"
    dispatcher._bus.publish_inbound.assert_called_once()
    call_args = dispatcher._bus.publish_inbound.call_args[0][0]
    assert call_args.content == "hello"
    assert call_args.channel.startswith("acp:")


@pytest.mark.asyncio
async def test_prompt_returns_error_when_session_not_found(dispatcher) -> None:
    dispatcher._session_service.get_session = MagicMock(return_value=None)
    req = JsonRpcRequest(id="6", method="prompt", params={"sessionId": "bad", "runId": "r1", "blocks": []})
    resp = await dispatcher.dispatch(req)
    assert isinstance(resp, JsonRpcError)
    assert resp.code == -32001


@pytest.mark.asyncio
async def test_cancel_notification_is_handled(dispatcher) -> None:
    notif = JsonRpcNotification(method="cancel", params={"runId": "r1", "sessionId": "s1"})
    # cancel は通知なので response は None
    result = await dispatcher.dispatch(notif)
    assert result is None


@pytest.mark.asyncio
async def test_unknown_method_returns_error(dispatcher) -> None:
    req = JsonRpcRequest(id="7", method="nonexistent", params={})
    resp = await dispatcher.dispatch(req)
    assert isinstance(resp, JsonRpcError)
    assert resp.code == -32601  # Method not found


@pytest.mark.asyncio
async def test_list_sessions_returns_dev_acp_sessions(dispatcher) -> None:
    session = _make_session("s1")
    dispatcher._session_service.list_sessions = MagicMock(return_value=[session])
    req = JsonRpcRequest(id="8", method="unstable_listSessions", params={})
    resp = await dispatcher.dispatch(req)
    assert isinstance(resp, JsonRpcResponse)
    assert resp.result["total"] == 1
    assert resp.result["sessions"][0]["sessionId"] == "s1"
