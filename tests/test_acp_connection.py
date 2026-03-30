import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from auraeve.transports.acp.connection import ACPConnectionHandler
from auraeve.transports.acp.dispatcher import ACPDispatcher
from auraeve.transports.acp.event_mapper import EventMapper
from auraeve.transports.acp.protocol import JsonRpcResponse, JsonRpcError
from auraeve.bus.events import OutboundMessage


class FakeWebSocket:
    """测试用 WebSocket 替身。"""
    def __init__(self, messages: list[str]):
        self._messages = list(messages)
        self.sent: list[str] = []
        self.closed = False

    async def receive_text(self) -> str:
        if not self._messages:
            raise StopIteration
        return self._messages.pop(0)

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def handler():
    dispatcher = MagicMock(spec=ACPDispatcher)
    dispatcher.dispatch = AsyncMock(return_value=JsonRpcResponse(id="1", result={"ok": True}))
    bus = MagicMock()
    bus.subscribe_outbound = MagicMock()
    bus.unsubscribe_outbound = MagicMock()
    mapper = EventMapper()
    return ACPConnectionHandler(dispatcher=dispatcher, bus=bus, event_mapper=mapper)


@pytest.mark.asyncio
async def test_handler_sends_jsonrpc_response(handler) -> None:
    ws = FakeWebSocket([
        json.dumps({"jsonrpc": "2.0", "id": "1", "method": "initialize", "params": {}}),
    ])
    handler._dispatcher.dispatch = AsyncMock(return_value=JsonRpcResponse(id="1", result={"protocolVersion": "1.0"}))

    await handler._process_single_message(ws, json.dumps({"jsonrpc": "2.0", "id": "1", "method": "initialize", "params": {}}))

    assert len(ws.sent) == 1
    sent = json.loads(ws.sent[0])
    assert sent["jsonrpc"] == "2.0"
    assert sent["result"]["protocolVersion"] == "1.0"


@pytest.mark.asyncio
async def test_handler_sends_error_response_on_dispatch_error(handler) -> None:
    handler._dispatcher.dispatch = AsyncMock(return_value=JsonRpcError(id="2", code=-32601, message="Method not found"))
    ws = FakeWebSocket([])

    await handler._process_single_message(
        ws,
        json.dumps({"jsonrpc": "2.0", "id": "2", "method": "bad", "params": {}}),
    )
    assert len(ws.sent) == 1
    sent = json.loads(ws.sent[0])
    assert sent["jsonrpc"] == "2.0"
    assert sent["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_on_outbound_pushes_acp_events(handler) -> None:
    ws = FakeWebSocket([])
    handler._ws = ws

    msg = OutboundMessage(channel="acp:s1", chat_id="s1", content="hello")
    await handler.on_outbound(msg)

    assert len(ws.sent) == 1
    ev = json.loads(ws.sent[0])
    assert ev["type"] == "message_chunk"
    assert ev["text"] == "hello"


@pytest.mark.asyncio
async def test_on_outbound_skips_empty_events(handler) -> None:
    ws = FakeWebSocket([])
    handler._ws = ws

    msg = OutboundMessage(channel="acp:s1", chat_id="s1", content="")
    await handler.on_outbound(msg)

    assert ws.sent == []


@pytest.mark.asyncio
async def test_new_session_auto_registers_outbound(handler) -> None:
    """newSession 成功响应后自动订阅 acp:{sessionId} 出站消息。"""
    ws = FakeWebSocket([])
    handler._dispatcher.dispatch = AsyncMock(return_value=JsonRpcResponse(
        id="3",
        result={"session": {"sessionId": "s42", "sessionKey": "k", "state": "idle", "metadata": {}}},
    ))
    await handler._process_single_message(
        ws,
        json.dumps({"jsonrpc": "2.0", "id": "3", "method": "newSession", "params": {}}),
    )
    assert "s42" in handler._session_ids
    handler._bus.subscribe_outbound.assert_called_once_with("acp:s42", handler.on_outbound)


@pytest.mark.asyncio
async def test_load_session_auto_registers_outbound(handler) -> None:
    """loadSession 成功响应后自动订阅 acp:{sessionId} 出站消息。"""
    ws = FakeWebSocket([])
    handler._dispatcher.dispatch = AsyncMock(return_value=JsonRpcResponse(
        id="4",
        result={"session": {"sessionId": "s99", "sessionKey": "k", "state": "idle", "metadata": {}}, "loaded": True},
    ))
    await handler._process_single_message(
        ws,
        json.dumps({"jsonrpc": "2.0", "id": "4", "method": "loadSession", "params": {"sessionId": "s99"}}),
    )
    assert "s99" in handler._session_ids
    handler._bus.subscribe_outbound.assert_called_once_with("acp:s99", handler.on_outbound)
