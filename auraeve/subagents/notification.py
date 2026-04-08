"""子智能体通知模型。"""
from __future__ import annotations

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
