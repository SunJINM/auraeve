from unittest.mock import MagicMock

import pytest

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.subagents.data.models import Task, TaskStatus
from auraeve.subagents.lifecycle import SubagentLifecycle


@pytest.mark.asyncio
async def test_lifecycle_marks_completed_and_enqueues_notification():
    store = MagicMock()
    queue = RuntimeCommandQueue()
    lifecycle = SubagentLifecycle(
        store=store,
        command_queue=queue,
    )
    task = Task(
        task_id="task-1",
        goal="分析任务",
        origin_channel="webui",
        origin_chat_id="chat-1",
        spawn_tool_call_id="call-1",
    )

    await lifecycle.mark_completed(task, "done")

    store.complete_task.assert_called_once()
    commands = queue.snapshot_all()
    assert len(commands) == 1
    assert commands[0].mode == "task-notification"
    assert commands[0].priority == "later"
    assert commands[0].payload["status"] == "completed"


@pytest.mark.asyncio
async def test_lifecycle_marks_failed_and_enqueues_failure_notification():
    store = MagicMock()
    queue = RuntimeCommandQueue()
    lifecycle = SubagentLifecycle(
        store=store,
        command_queue=queue,
    )
    task = Task(
        task_id="task-2",
        goal="分析失败任务",
        origin_channel="webui",
        origin_chat_id="chat-2",
        spawn_tool_call_id="call-2",
    )

    await lifecycle.mark_failed(task, "boom")

    store.update_task_status.assert_called_once_with("task-2", TaskStatus.FAILED)
    commands = queue.snapshot_all()
    assert len(commands) == 1
    assert commands[0].payload["status"] == "failed"
