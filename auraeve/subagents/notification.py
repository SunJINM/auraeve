"""子智能体通知模型与兼容队列。"""
from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class TaskNotification:
    """子智能体完成通知。"""
    task_id: str
    agent_type: str
    goal: str
    status: str          # completed / failed / killed
    result: str
    spawn_tool_call_id: str
    duration_ms: int = 0
    tool_use_count: int = 0
    total_tokens: int = 0

    def to_payload(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "agent_type": self.agent_type,
            "goal": self.goal,
            "status": self.status,
            "result": self.result,
            "spawn_tool_call_id": self.spawn_tool_call_id,
            "duration_ms": self.duration_ms,
            "tool_use_count": self.tool_use_count,
            "total_tokens": self.total_tokens,
        }


class NotificationQueue:
    """线程安全的通知队列。"""

    def __init__(self) -> None:
        self._queue: list[TaskNotification] = []
        self._lock = threading.Lock()

    def enqueue(self, notification: TaskNotification) -> None:
        with self._lock:
            self._queue.append(notification)

    def drain(self) -> list[TaskNotification]:
        """取出所有待处理通知并清空队列。"""
        with self._lock:
            result = self._queue.copy()
            self._queue.clear()
            return result

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def has_pending(self) -> bool:
        with self._lock:
            return len(self._queue) > 0
