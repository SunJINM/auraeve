"""子智能体异步生命周期管理。"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

from .data.models import Task, TaskStatus
from .data.repositories import SubagentStore
from .notification import NotificationQueue, TaskNotification

logger = logging.getLogger(__name__)


class SubagentLifecycle:
    """处理子智能体的完成、失败、取消与结果注入。"""

    def __init__(
        self,
        *,
        store: SubagentStore,
        notification_queue: NotificationQueue,
        kernel_resume_callback: Callable | None = None,
    ) -> None:
        self._store = store
        self._notification_queue = notification_queue
        self._kernel_resume_callback = kernel_resume_callback
        self._injected_ids: set[str] = set()
        self._inject_lock = asyncio.Lock()

    def set_kernel_resume_callback(self, callback: Callable | None) -> None:
        self._kernel_resume_callback = callback

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
        self._notification_queue.enqueue(notification)
        await self._try_inject_result(task, notification)
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
        self._notification_queue.enqueue(notification)
        await self._try_inject_result(task, notification)
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
        self._notification_queue.enqueue(notification)
        return notification

    async def _try_inject_result(
        self,
        task: Task,
        notification: TaskNotification,
    ) -> None:
        if not self._kernel_resume_callback:
            return
        if not task.spawn_tool_call_id:
            return

        async with self._inject_lock:
            if task.task_id in self._injected_ids:
                return
            self._injected_ids.add(task.task_id)

        synthetic = self._notification_queue.build_synthetic_messages(notification)
        try:
            await self._kernel_resume_callback(
                channel=task.origin_channel,
                chat_id=task.origin_chat_id,
                synthetic_messages=synthetic,
            )
        except Exception:
            logger.exception("注入子智能体结果到母体失败: %s", task.task_id)
