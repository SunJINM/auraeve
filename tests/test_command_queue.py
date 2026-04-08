from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.agent_runtime.command_types import QueuedCommand


def _cmd(
    command_id: str,
    mode: str,
    priority: str,
    *,
    agent_id: str | None = None,
) -> QueuedCommand:
    return QueuedCommand(
        id=command_id,
        session_key="s1",
        source="test",
        mode=mode,
        priority=priority,
        payload={"text": command_id},
        origin={"kind": "test"},
        agent_id=agent_id,
    )


def test_queue_dequeues_by_priority_then_fifo() -> None:
    queue = RuntimeCommandQueue()
    queue.enqueue_command(_cmd("later-1", "prompt", "later"))
    queue.enqueue_command(_cmd("next-1", "prompt", "next"))
    queue.enqueue_command(_cmd("now-1", "prompt", "now"))
    queue.enqueue_command(_cmd("next-2", "prompt", "next"))

    assert queue.dequeue_next().id == "now-1"
    assert queue.dequeue_next().id == "next-1"
    assert queue.dequeue_next().id == "next-2"
    assert queue.dequeue_next().id == "later-1"


def test_snapshot_for_main_thread_filters_agent_scope_and_priority() -> None:
    queue = RuntimeCommandQueue()
    queue.enqueue_command(_cmd("main-prompt", "prompt", "next"))
    queue.enqueue_command(_cmd("sub-note", "task-notification", "next", agent_id="sub-1"))
    queue.enqueue_command(_cmd("later-note", "task-notification", "later"))

    snapshot = queue.snapshot_for_scope(
        max_priority="next",
        agent_id=None,
        is_main_thread=True,
    )

    assert [cmd.id for cmd in snapshot] == ["main-prompt"]


def test_snapshot_for_subagent_only_keeps_own_task_notifications() -> None:
    queue = RuntimeCommandQueue()
    queue.enqueue_command(_cmd("main-prompt", "prompt", "next"))
    queue.enqueue_command(_cmd("sub-1-note", "task-notification", "next", agent_id="sub-1"))
    queue.enqueue_command(_cmd("sub-2-note", "task-notification", "next", agent_id="sub-2"))

    snapshot = queue.snapshot_for_scope(
        max_priority="next",
        agent_id="sub-1",
        is_main_thread=False,
    )

    assert [cmd.id for cmd in snapshot] == ["sub-1-note"]


def test_remove_commands_only_removes_exact_objects() -> None:
    queue = RuntimeCommandQueue()
    first = _cmd("c1", "prompt", "next")
    second = _cmd("c2", "prompt", "next")
    queue.enqueue_command(first)
    queue.enqueue_command(second)

    queue.remove_commands([first])

    remaining = queue.snapshot_all()
    assert [cmd.id for cmd in remaining] == ["c2"]


def test_snapshot_for_scope_filters_session_key() -> None:
    queue = RuntimeCommandQueue()
    queue.enqueue_command(
        QueuedCommand(
            id="s1-cmd",
            session_key="webui:s1",
            source="webui",
            mode="prompt",
            priority="next",
            payload={"content": "one"},
            origin={"kind": "user"},
        )
    )
    queue.enqueue_command(
        QueuedCommand(
            id="s2-cmd",
            session_key="webui:s2",
            source="webui",
            mode="prompt",
            priority="next",
            payload={"content": "two"},
            origin={"kind": "user"},
        )
    )

    snapshot = queue.snapshot_for_scope(
        max_priority="next",
        agent_id=None,
        is_main_thread=True,
        session_key="webui:s1",
    )

    assert [cmd.id for cmd in snapshot] == ["s1-cmd"]
