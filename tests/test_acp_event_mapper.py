from auraeve.bus.events import OutboundMessage
from auraeve.transports.acp.event_mapper import EventMapper


def _make_outbound(content: str, metadata: dict | None = None) -> OutboundMessage:
    return OutboundMessage(
        channel="acp:s1",
        chat_id="s1",
        content=content,
        metadata=metadata or {},
    )


def test_plain_text_maps_to_message_chunk() -> None:
    mapper = EventMapper()
    events = mapper.map(_make_outbound("hello world"))
    assert len(events) == 1
    ev = events[0]
    assert ev["type"] == "message_chunk"
    assert ev["text"] == "hello world"


def test_tool_call_start_event() -> None:
    mapper = EventMapper()
    msg = _make_outbound("", metadata={"acp_event": "tool_call_started", "tool_name": "read_file", "tool_call_id": "tc1"})
    events = mapper.map(msg)
    assert len(events) == 1
    assert events[0]["type"] == "tool_call_started"
    assert events[0]["toolName"] == "read_file"
    assert events[0]["toolCallId"] == "tc1"
    assert events[0]["input"] == {}


def test_tool_call_finish_event() -> None:
    mapper = EventMapper()
    msg = _make_outbound("result text", metadata={"acp_event": "tool_call_finished", "tool_call_id": "tc1"})
    events = mapper.map(msg)
    assert len(events) == 1
    assert events[0]["type"] == "tool_call_finished"
    assert events[0]["toolCallId"] == "tc1"
    assert events[0]["result"] == "result text"


def test_done_event() -> None:
    mapper = EventMapper()
    msg = _make_outbound("", metadata={"acp_event": "done", "stop_reason": "stop"})
    events = mapper.map(msg)
    assert len(events) == 1
    assert events[0]["type"] == "done"
    assert events[0]["stopReason"] == "stop"


def test_empty_content_with_no_acp_event_returns_empty() -> None:
    mapper = EventMapper()
    events = mapper.map(_make_outbound(""))
    assert events == []


def test_usage_update_event() -> None:
    mapper = EventMapper()
    msg = _make_outbound("", metadata={
        "acp_event": "usage_update",
        "input_tokens": 100,
        "output_tokens": 50,
    })
    events = mapper.map(msg)
    assert len(events) == 1
    assert events[0]["type"] == "usage_update"
    assert events[0]["inputTokens"] == 100
    assert events[0]["outputTokens"] == 50


def test_tool_call_start_event_with_input() -> None:
    mapper = EventMapper()
    msg = _make_outbound("", metadata={
        "acp_event": "tool_call_started",
        "tool_name": "write_file",
        "tool_call_id": "tc2",
        "input": {"path": "/tmp/file.txt", "content": "hello"},
    })
    events = mapper.map(msg)
    assert len(events) == 1
    assert events[0]["type"] == "tool_call_started"
    assert events[0]["input"] == {"path": "/tmp/file.txt", "content": "hello"}
