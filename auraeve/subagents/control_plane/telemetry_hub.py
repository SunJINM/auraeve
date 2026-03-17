"""TelemetryHub：分布式追踪、事件聚合。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from auraeve.subagents.data.models import TaskEvent
from auraeve.subagents.data.repositories import SubagentDB


def new_span_id() -> str:
    return uuid.uuid4().hex[:16]


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_span_id: str
    operation: str
    node_id: str
    status: str
    duration_ms: float
    metadata: dict


class TelemetryHub:
    """基于 task_events 表的追踪记录器。"""

    def __init__(self, db: SubagentDB) -> None:
        self._db = db

    def record_span(
        self,
        task_id: str,
        trace_id: str,
        span_id: str,
        parent_span_id: str,
        operation: str,
        node_id: str,
        status: str,
        duration_ms: float,
        metadata: dict | None = None,
    ) -> None:
        seq = self._db.get_next_seq(task_id)
        event = TaskEvent(
            task_id=task_id,
            seq=seq,
            event_type="span",
            payload={
                "operation": operation,
                "node_id": node_id,
                "status": status,
                "duration_ms": duration_ms,
                **(metadata or {}),
            },
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
        )
        self._db.append_event(event)

    def record_state_change(
        self,
        task_id: str,
        trace_id: str,
        from_status: str,
        to_status: str,
        reason: str = "",
    ) -> None:
        seq = self._db.get_next_seq(task_id)
        event = TaskEvent(
            task_id=task_id,
            seq=seq,
            event_type="state_change",
            payload={"from": from_status, "to": to_status, "reason": reason},
            trace_id=trace_id,
            span_id=new_span_id(),
        )
        self._db.append_event(event)

    def get_trace(self, task_id: str) -> list[TaskEvent]:
        return self._db.get_events(task_id)
