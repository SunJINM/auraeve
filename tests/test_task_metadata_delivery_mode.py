from auraeve.subagents.data.models import Task
from auraeve.subagents.control_plane.orchestrator import _resolve_delivery_mode


def test_task_metadata_dev_acp_resolves_dev_transcript() -> None:
    task = Task(
        task_id="t1",
        goal="do something",
        metadata={"session_type": "dev_acp"},
    )
    assert _resolve_delivery_mode(task.metadata) == "dev_transcript"


def test_task_metadata_absent_resolves_mother_chat() -> None:
    task = Task(task_id="t2", goal="normal task")
    assert _resolve_delivery_mode(task.metadata) == "mother_chat"
