"""子智能体通知队列。

对标 Claude Code 的 messageQueueManager.ts + enqueueAgentNotification。
子智能体完成后生成 TaskNotification，母体在检查点消费并注入对话上下文。
"""
from __future__ import annotations

import json
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

    @staticmethod
    def build_synthetic_messages(notification: TaskNotification) -> list[dict]:
        """将通知转为 synthetic tool_use + tool_result 消息对。"""
        tool_use_msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": notification.spawn_tool_call_id,
                "type": "function",
                "function": {
                    "name": "subagent_result",
                    "arguments": json.dumps({
                        "task_id": notification.task_id,
                        "agent_type": notification.agent_type,
                        "goal": notification.goal,
                    }, ensure_ascii=False),
                },
            }],
        }

        tool_result_msg = {
            "role": "tool",
            "tool_call_id": notification.spawn_tool_call_id,
            "name": "subagent_result",
            "content": json.dumps({
                "status": notification.status,
                "result": notification.result,
                "source": "async_subagent_callback",
                "agent_type": notification.agent_type,
                "task_id": notification.task_id,
            }, ensure_ascii=False),
        }

        return [tool_use_msg, tool_result_msg]
