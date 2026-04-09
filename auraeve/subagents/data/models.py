"""子智能体数据模型。

对标 Claude Code 的 LocalAgentTaskState，去掉了远程节点、审批、
记忆增量、DAG 依赖、Saga 补偿等不再需要的概念。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


# ── 状态枚举 ──────────────────────────────────────────────

class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


TERMINAL_STATUSES = frozenset({
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.KILLED,
})

_VALID_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.QUEUED: frozenset({TaskStatus.RUNNING, TaskStatus.KILLED}),
    TaskStatus.RUNNING: frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.KILLED}),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.KILLED: frozenset(),
}

STATUS_ICON: dict[TaskStatus, str] = {
    TaskStatus.QUEUED: "⏳",
    TaskStatus.RUNNING: "🔄",
    TaskStatus.COMPLETED: "✅",
    TaskStatus.FAILED: "❌",
    TaskStatus.KILLED: "⚫",
}


def is_terminal(status: TaskStatus) -> bool:
    return status in TERMINAL_STATUSES


def is_valid_transition(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    return to_status in _VALID_TRANSITIONS.get(from_status, frozenset())


# ── 数据类 ────────────────────────────────────────────────

@dataclass
class TaskBudget:
    """子智能体执行预算。"""
    max_steps: int = 50
    max_duration_s: int = 600
    max_tool_calls: int = 100


@dataclass
class Task:
    """子智能体任务。"""
    task_id: str
    goal: str
    agent_type: str = "general-purpose"
    status: TaskStatus = TaskStatus.QUEUED
    priority: int = 5
    budget: TaskBudget = field(default_factory=TaskBudget)
    name: str = ""
    description: str = ""
    role_prompt: str = ""
    result: str = ""
    origin_channel: str = ""
    origin_chat_id: str = ""
    spawn_tool_call_id: str = ""
    run_in_background: bool = False
    execution_mode: str = "sync"
    context_mode: str = "fresh"
    session_key: str = ""
    parent_thread_id: str = ""
    parent_task_id: str = ""
    seed_messages_json: str = ""
    worktree_path: str = ""
    worktree_branch: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0


@dataclass
class ProgressTracker:
    """子智能体执行进度追踪。"""
    tool_use_count: int = 0
    total_tokens: int = 0
    recent_activities: list[dict] = field(default_factory=list)
    duration_ms: int = 0

    def record_activity(self, tool_name: str, tool_input: dict) -> None:
        self.tool_use_count += 1
        self.recent_activities.append({"tool": tool_name, "input": tool_input})
        if len(self.recent_activities) > 5:
            self.recent_activities.pop(0)
