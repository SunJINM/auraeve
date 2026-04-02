"""子智能体异步生命周期管理。"""
from __future__ import annotations

import logging
import time

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.agent_runtime.command_types import QueuedCommand

from .data.models import Task, TaskStatus
from .data.repositories import SubagentStore
from .notification import TaskNotification

logger = logging.getLogger(__name__)


class SubagentLifecycle:
    """处理子智能体的完成、失败、取消与结果注入。"""

    def __init__(
        self,
        *,
        store: SubagentStore,
        command_queue: RuntimeCommandQueue,
    ) -> None:
        self._store = store
        self._command_queue = command_queue

    async def mark_completed(self, task: Task, result: str) -> TaskNotification:
        self._store.complete_task(
            task.task_id,
            result=result,
            completed_at=time.time(),
        )
        notification = TaskNotification(
            task_id=task.task_id,
            agent_type=task.agent_type,
            goal=task.goal,
            status="completed",
            result=result,
            spawn_tool_call_id=task.spawn_tool_call_id,
        )
        self._enqueue_notification(task, notification)
        return notification

    async def mark_failed(self, task: Task, error_msg: str) -> TaskNotification:
        self._store.update_task_status(task.task_id, TaskStatus.FAILED)
        notification = TaskNotification(
            task_id=task.task_id,
            agent_type=task.agent_type,
            goal=task.goal,
            status="failed",
            result=error_msg,
            spawn_tool_call_id=task.spawn_tool_call_id,
        )
        self._enqueue_notification(task, notification)
        return notification

    async def mark_cancelled(self, task: Task) -> TaskNotification:
        self._store.update_task_status(task.task_id, TaskStatus.KILLED)
        notification = TaskNotification(
            task_id=task.task_id,
            agent_type=task.agent_type,
            goal=task.goal,
            status="killed",
            result="任务被取消",
            spawn_tool_call_id=task.spawn_tool_call_id,
        )
        self._enqueue_notification(task, notification)
        return notification

    def _enqueue_notification(
        self,
        task: Task,
        notification: TaskNotification,
    ) -> None:
        session_key = f"{task.origin_channel}:{task.origin_chat_id}".strip(":")
        self._command_queue.enqueue_command(
            QueuedCommand(
                session_key=session_key or task.task_id,
                source="subagent",
                mode="task-notification",
                priority="later",
                payload=notification.to_payload(),
                origin={"kind": "task-notification", "is_system_generated": True},
            )
        )
