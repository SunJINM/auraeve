from unittest.mock import AsyncMock, MagicMock

import pytest

from auraeve.subagents.data.models import Task, TaskStatus
from auraeve.subagents.lifecycle import SubagentLifecycle
from auraeve.subagents.notification import NotificationQueue


@pytest.mark.asyncio
async def test_lifecycle_marks_completed_and_injects_result():
    store = MagicMock()
    queue = NotificationQueue()
    callback = AsyncMock()
    lifecycle = SubagentLifecycle(
        store=store,
        notification_queue=queue,
        kernel_resume_callback=callback,
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
    assert queue.pending_count == 1
    callback.assert_awaited_once()
    kwargs = callback.await_args.kwargs
    assert kwargs["channel"] == "webui"
    assert kwargs["chat_id"] == "chat-1"
    assert len(kwargs["synthetic_messages"]) == 2


@pytest.mark.asyncio
async def test_lifecycle_marks_failed_and_enqueues_failure_notification():
    store = MagicMock()
    queue = NotificationQueue()
    callback = AsyncMock()
    lifecycle = SubagentLifecycle(
        store=store,
        notification_queue=queue,
        kernel_resume_callback=callback,
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
    assert queue.pending_count == 1
    callback.assert_awaited_once()
