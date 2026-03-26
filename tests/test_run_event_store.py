from pathlib import Path

from auraeve.domain.runs.event_store import RunEventStore
from auraeve.domain.runs.models import RunEvent


def test_run_event_store_append_and_list(tmp_path: Path) -> None:
    store = RunEventStore(tmp_path / "events.jsonl")
    event = RunEvent(
        event_id="e1",
        session_id="s1",
        run_id="r1",
        event_type="user_prompt",
        payload={"text": "hello"},
    )

    store.append(event)

    items = store.list_for_session("s1")
    assert len(items) == 1
    assert items[0].payload["text"] == "hello"


def test_run_event_store_returns_empty_list_when_file_missing(tmp_path: Path) -> None:
    store = RunEventStore(tmp_path / "missing.jsonl")

    assert store.list_for_session("s1") == []


def test_run_event_store_filters_by_session_id(tmp_path: Path) -> None:
    store = RunEventStore(tmp_path / "events.jsonl")
    first = RunEvent(
        event_id="e1",
        session_id="s1",
        run_id="r1",
        event_type="user_prompt",
        payload={"text": "hello"},
    )
    second = RunEvent(
        event_id="e2",
        session_id="s2",
        run_id="r2",
        event_type="assistant_output",
        payload={"text": "world"},
    )

    store.append(first)
    store.append(second)

    items = store.list_for_session("s2")
    assert len(items) == 1
    assert items[0].event_id == "e2"


def test_run_event_store_skips_bad_lines(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        '{"event_id":"e1","session_id":"s1","run_id":"r1","event_type":"user_prompt","payload":{"text":"hello"}}\n'
        "not-json\n"
        '{"event_id":"e2","session_id":"s1","run_id":"r2","event_type":"assistant_output","payload":{"text":"world"}}\n',
        encoding="utf-8",
    )
    store = RunEventStore(path)

    items = store.list_for_session("s1")
    assert [item.event_id for item in items] == ["e1", "e2"]
