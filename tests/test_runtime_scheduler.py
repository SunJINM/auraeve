import asyncio

import pytest

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.agent_runtime.command_types import QueuedCommand
from auraeve.agent_runtime.runtime_scheduler import RuntimeScheduler


@pytest.mark.asyncio
async def test_scheduler_runs_next_command_when_idle() -> None:
    queue = RuntimeCommandQueue()
    seen: list[str] = []

    async def runner(command: QueuedCommand) -> None:
        seen.append(command.id)

    scheduler = RuntimeScheduler(queue=queue, run_command=runner)
    await scheduler.start()
    queue.enqueue_command(
        QueuedCommand(
            id="cmd-1",
            session_key="s1",
            source="test",
            mode="prompt",
            priority="next",
            payload={"content": "hello"},
            origin={"kind": "user"},
        )
    )

    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert seen == ["cmd-1"]


def test_scheduler_checkpoint_snapshot_uses_queue_scope() -> None:
    queue = RuntimeCommandQueue()
    queue.enqueue_command(
        QueuedCommand(
            id="cmd-1",
            session_key="s1",
            source="test",
            mode="prompt",
            priority="next",
            payload={"content": "hello"},
            origin={"kind": "user"},
        )
    )

    scheduler = RuntimeScheduler(queue=queue, run_command=None)
    snapshot = scheduler.snapshot_for_checkpoint(
        agent_id=None,
        is_main_thread=True,
        max_priority="next",
    )

    assert [cmd.id for cmd in snapshot] == ["cmd-1"]
