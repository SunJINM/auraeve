import asyncio
from pathlib import Path

from auraeve.runtimes.acp.runtime import ACPRuntime
from auraeve.domain.runs.event_store import RunEventStore
from auraeve.runtimes.acp.contracts import ACPRunRequest
from auraeve.services.run_service import RunService


def test_acp_runtime_exposes_runtime_name(tmp_path: Path) -> None:
    runtime = ACPRuntime(RunService(RunEventStore(tmp_path / "events.jsonl")))

    assert runtime.name == "acp"


def test_acp_runtime_records_prompt_event_and_separates_metadata(tmp_path: Path) -> None:
    event_store = RunEventStore(tmp_path / "events.jsonl")
    service = RunService(event_store)
    runtime = ACPRuntime(service)
    request = ACPRunRequest(
        session_id="s1",
        prompt="hello",
        metadata={"source": "acp"},
    )

    out = asyncio.run(runtime.start_run(request))
    items = service.list_events("s1")

    assert out.session_id == "s1"
    assert out.status == "accepted"
    assert out.metadata["request"] == {"source": "acp"}
    assert "run_id" in out.metadata["runtime"]
    assert len(items) == 1
    assert items[0].event_type == "user_prompt"
    assert items[0].payload["prompt"] == "hello"
    assert items[0].payload["metadata"] == {"source": "acp"}
