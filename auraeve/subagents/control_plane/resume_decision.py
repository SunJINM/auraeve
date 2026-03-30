"""决定子体完成后母体是否立即续写。"""
from __future__ import annotations

from enum import Enum

from auraeve.subagents.data.models import Task, TaskStatus


class ResumeDecision(Enum):
    RESUME_AND_REPLY = "resume_and_reply"   # 立即续写并回复用户
    WAIT_FOR_OTHERS = "wait_for_others"     # fan-out 中有兄弟任务未完成
    STORE_ONLY = "store_only"               # 无 origin，不触发 LLM


_TERMINAL = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELED,
    TaskStatus.TIMED_OUT,
    TaskStatus.COMPENSATED,
}


def decide_resume(task: Task, db) -> ResumeDecision:
    """根据任务状态和 DAG 情况决定是否续写母体。"""
    if not task.origin_channel:
        return ResumeDecision.STORE_ONLY

    if not task.trace_id:
        return ResumeDecision.RESUME_AND_REPLY

    siblings = db.list_tasks_by_trace(task.trace_id)
    if len(siblings) <= 1:
        return ResumeDecision.RESUME_AND_REPLY

    pending = [t for t in siblings if t.status not in _TERMINAL]
    if pending:
        return ResumeDecision.WAIT_FOR_OTHERS

    return ResumeDecision.RESUME_AND_REPLY
