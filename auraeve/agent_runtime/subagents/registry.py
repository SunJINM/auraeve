"""SubagentRegistry：子代理全生命周期状态机 + 任务台账。

状态机（无 paused）：
  created → running → completed
                    → failed
                    → cancelled
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SubagentStatus(str, Enum):
    CREATED   = "created"
    RUNNING   = "running"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED    = "failed"


_STATUS_ICON = {
    SubagentStatus.CREATED:   "🕐",
    SubagentStatus.RUNNING:   "🔄",
    SubagentStatus.CANCELLED: "⚫",
    SubagentStatus.COMPLETED: "✅",
    SubagentStatus.FAILED:    "❌",
}


@dataclass
class SubagentRecord:
    """单个子代理的运行时台账。"""
    id: str
    label: str
    task: str
    status: SubagentStatus
    started_at: float
    origin_channel: str
    origin_chat_id: str
    finished_at: Optional[float] = None
    error_reason: Optional[str] = None
    # 状态转换审计轨迹
    transitions: list[dict] = field(default_factory=list)

    def elapsed(self) -> float:
        end = self.finished_at or time.time()
        return round(end - self.started_at, 1)

    def to_summary(self) -> str:
        icon = _STATUS_ICON.get(self.status, "❓")
        return f"{icon} [{self.id}] {self.label}（{self.status.value}，{self.elapsed()}s）"

    def _record_transition(self, new_status: SubagentStatus, reason: str = "") -> None:
        self.transitions.append({
            "from": self.status.value,
            "to": new_status.value,
            "at": time.time(),
            "reason": reason,
        })


class SubagentRegistry:
    """
    子代理任务注册表。

    职责：
    - 注册任务（created → running）
    - 查询任务状态
    - 更新终态（completed / failed / cancelled）
    - 列出任务（支持时间过滤）
    - 统计运行中数量（全局 / 按会话）
    """

    def __init__(self) -> None:
        self._records: dict[str, SubagentRecord] = {}

    def register(self, record: SubagentRecord) -> None:
        """注册新任务（应在 created 状态下调用）。"""
        self._records[record.id] = record

    def get(self, task_id: str) -> SubagentRecord | None:
        return self._records.get(task_id)

    def update_status(
        self,
        task_id: str,
        status: SubagentStatus,
        finished_at: float | None = None,
        error_reason: str | None = None,
        reason: str = "",
    ) -> None:
        """更新任务状态，记录转换轨迹。"""
        record = self._records.get(task_id)
        if record is None:
            return
        record._record_transition(status, reason)
        record.status = status
        if finished_at is not None:
            record.finished_at = finished_at
        if error_reason is not None:
            record.error_reason = error_reason

    def list_tasks(self, recent_minutes: float | None = None) -> list[SubagentRecord]:
        """返回任务列表，可按启动时间过滤。"""
        tasks = list(self._records.values())
        if recent_minutes is not None:
            cutoff = time.time() - recent_minutes * 60
            tasks = [t for t in tasks if t.started_at >= cutoff]
        return tasks

    def get_running_count(self, session_key: str | None = None) -> int:
        """统计运行中任务数（session_key 为 None 时统计全局）。"""
        running = [r for r in self._records.values() if r.status == SubagentStatus.RUNNING]
        if session_key is None:
            return len(running)
        return sum(
            1 for r in running
            if f"{r.origin_channel}:{r.origin_chat_id}" == session_key
        )
