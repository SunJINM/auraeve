from pathlib import Path

from auraeve.domain.runs.event_store import RunEventStore
from auraeve.services.run_service import RunService


def test_run_service_records_prompt_event(tmp_path: Path) -> None:
    service = RunService(RunEventStore(tmp_path / "events"))

    run_id = service.record_prompt("s1", "hello")

    items = service.list_events("s1")
    assert run_id
    assert len(items) == 1
    assert items[0].session_id == "s1"
    assert items[0].event_type == "user_prompt"
    assert items[0].payload["prompt"] == "hello"
    assert items[0].payload["metadata"] == {}


def test_run_service_filters_events_by_session_id(tmp_path: Path) -> None:
    service = RunService(RunEventStore(tmp_path / "events"))

    service.record_prompt("s1", "hello")
    service.record_prompt("s2", "world")

    items = service.list_events("s2")
    assert len(items) == 1
    assert items[0].session_id == "s2"


def test_run_service_preserves_prompt_metadata(tmp_path: Path) -> None:
    service = RunService(RunEventStore(tmp_path / "events"))

    service.record_prompt("s1", "hello", {"source": "acp"})

    items = service.list_events("s1")
    assert items[0].payload["metadata"] == {"source": "acp"}

