from pathlib import Path

from auraeve.domain.runs.event_store import RunEventStore
from auraeve.domain.runs.models import RunEvent


def test_run_event_store_uses_per_session_file(tmp_path: Path) -> None:
    store = RunEventStore(tmp_path)
    event = RunEvent(
        event_id="e1",
        session_id="s1",
        run_id="r1",
        event_type="user_prompt",
        payload={"text": "hello"},
    )

    store.append(event)

    assert (tmp_path / "s1.jsonl").exists()
    items = store.list_for_session("s1")
    assert len(items) == 1
    assert items[0].payload["text"] == "hello"


def test_run_event_store_isolates_sessions(tmp_path: Path) -> None:
    store = RunEventStore(tmp_path)
    store.append(RunEvent(event_id="e1", session_id="s1", run_id="r1", event_type="user_prompt", payload={}))
    store.append(RunEvent(event_id="e2", session_id="s2", run_id="r2", event_type="user_prompt", payload={}))

    assert len(store.list_for_session("s1")) == 1
    assert len(store.list_for_session("s2")) == 1


def test_run_event_store_returns_empty_list_when_session_missing(tmp_path: Path) -> None:
    store = RunEventStore(tmp_path)
    assert store.list_for_session("nonexistent") == []


def test_run_event_store_skips_bad_lines(tmp_path: Path) -> None:
    store = RunEventStore(tmp_path)
    # 手动写入含坏行的文件
    path = tmp_path / "s1.jsonl"
    path.write_text(
        '{"event_id":"e1","session_id":"s1","run_id":"r1","event_type":"user_prompt","payload":{"text":"hello"}}\n'
        "not-json\n"
        '{"event_id":"e2","session_id":"s1","run_id":"r2","event_type":"assistant_output","payload":{"text":"world"}}\n',
        encoding="utf-8",
    )

    items = store.list_for_session("s1")
    assert [item.event_id for item in items] == ["e1", "e2"]
