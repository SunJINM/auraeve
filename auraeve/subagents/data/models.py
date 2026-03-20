"""子体系统数据模型。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── 任务状态机 ──────────────────────────────────────────────────────────────


class TaskStatus(str, Enum):
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    INPUT_REQUIRED = "input_required"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    TIMED_OUT = "timed_out"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"


# 合法状态迁移表
_VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.QUEUED: {TaskStatus.DISPATCHED, TaskStatus.CANCELED},
    TaskStatus.DISPATCHED: {TaskStatus.RUNNING, TaskStatus.CANCELED},
    TaskStatus.RUNNING: {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELED,
        TaskStatus.PAUSED,
        TaskStatus.INPUT_REQUIRED,
        TaskStatus.TIMED_OUT,
    },
    TaskStatus.INPUT_REQUIRED: {
        TaskStatus.RUNNING,
        TaskStatus.FAILED,
        TaskStatus.CANCELED,
        TaskStatus.TIMED_OUT,
    },
    TaskStatus.PAUSED: {TaskStatus.RUNNING, TaskStatus.CANCELED, TaskStatus.TIMED_OUT},
    TaskStatus.FAILED: {TaskStatus.COMPENSATING},
    TaskStatus.CANCELED: {TaskStatus.COMPENSATING},
    TaskStatus.TIMED_OUT: {TaskStatus.COMPENSATING},
    TaskStatus.COMPENSATING: {TaskStatus.COMPENSATED, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.COMPENSATED: set(),
}

TERMINAL_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.COMPENSATED,
    TaskStatus.FAILED,
    TaskStatus.CANCELED,
    TaskStatus.TIMED_OUT,
}


def is_valid_transition(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    return to_status in _VALID_TRANSITIONS.get(from_status, set())


def is_terminal(status: TaskStatus) -> bool:
    """判断任务是否处于终态。
    FAILED/CANCELED/TIMED_OUT 虽然可以迁移到 COMPENSATING，
    但在没有补偿动作时视为终态。
    """
    return status in TERMINAL_STATUSES


# ── 风险等级 ────────────────────────────────────────────────────────────────


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── 审批状态 ────────────────────────────────────────────────────────────────


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISED = "revised"
    TIMED_OUT = "timed_out"


# ── 记忆增量类型 ────────────────────────────────────────────────────────────


class DeltaType(str, Enum):
    FACT = "fact"
    EXPERIENCE = "experience"
    OBSERVATION = "observation"


class MergeStatus(str, Enum):
    PENDING = "pending"
    MERGED = "merged"
    CONFLICT = "conflict"
    REJECTED = "rejected"


# ── 数据模型 ────────────────────────────────────────────────────────────────


@dataclass
class TaskBudget:
    max_steps: int = 50
    max_duration_s: int = 600
    max_tool_calls: int = 100
    max_tokens: int = 120_000

    def to_dict(self) -> dict:
        return {
            "max_steps": self.max_steps,
            "max_duration_s": self.max_duration_s,
            "max_tool_calls": self.max_tool_calls,
            "max_tokens": self.max_tokens,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TaskBudget:
        return cls(**{k: d[k] for k in ("max_steps", "max_duration_s", "max_tool_calls", "max_tokens") if k in d})


@dataclass
class Task:
    task_id: str
    goal: str
    assigned_node_id: str = ""
    priority: int = 5
    status: TaskStatus = TaskStatus.QUEUED
    depends_on: list[str] = field(default_factory=list)
    budget: TaskBudget = field(default_factory=TaskBudget)
    policy_profile: str = "default"
    result: str = ""
    compensate_action: str | None = None
    trace_id: str = ""
    origin_channel: str = ""
    origin_chat_id: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex[:12]

    @staticmethod
    def new_trace_id() -> str:
        return f"trace-{uuid.uuid4().hex[:16]}"


@dataclass
class TaskEvent:
    task_id: str
    seq: int
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    span_id: str = ""
    parent_span_id: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class Approval:
    approval_id: str
    task_id: str
    action_desc: str
    risk_level: RiskLevel
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_by: str = ""
    decided_at: float = 0.0
    created_at: float = field(default_factory=time.time)

    @staticmethod
    def new_id() -> str:
        return f"apv-{uuid.uuid4().hex[:12]}"


@dataclass
class TaskArtifact:
    artifact_id: str
    task_id: str
    name: str
    content_type: str = "text/plain"
    data: bytes = b""
    created_at: float = field(default_factory=time.time)

    @staticmethod
    def new_id() -> str:
        return f"art-{uuid.uuid4().hex[:12]}"


@dataclass
class NodeSession:
    node_id: str
    display_name: str = ""
    platform: str = ""
    capabilities: list[dict] = field(default_factory=list)
    connected_at: float = 0.0
    disconnected_at: float = 0.0
    is_online: bool = False


@dataclass
class MemoryDelta:
    delta_id: str
    task_id: str
    node_id: str
    delta_type: DeltaType
    content: str
    confidence: float = 1.0
    merge_status: MergeStatus = MergeStatus.PENDING
    created_at: float = field(default_factory=time.time)

    @staticmethod
    def new_id() -> str:
        return f"md-{uuid.uuid4().hex[:12]}"


@dataclass
class KnowledgeTriple:
    triple_id: str
    subject: str
    predicate: str
    object: str
    source_task_id: str = ""
    source_node_id: str = ""
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)

    @staticmethod
    def new_id() -> str:
        return f"kt-{uuid.uuid4().hex[:12]}"


@dataclass
class CapabilityScore:
    node_id: str
    capability_domain: str
    success_count: int = 0
    fail_count: int = 0
    avg_duration_s: float = 0.0
    last_updated: float = field(default_factory=time.time)

    @property
    def score(self) -> float:
        total = self.success_count + self.fail_count
        if total == 0:
            return 0.5
        return self.success_count / total


@dataclass
class Capability:
    """子体能力声明。"""
    name: str
    schema: dict[str, Any] = field(default_factory=dict)
    risk: RiskLevel = RiskLevel.LOW
    idempotent: bool = False
    resource: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "schema": self.schema,
            "risk": self.risk.value,
            "idempotent": self.idempotent,
            "resource": self.resource,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Capability:
        return cls(
            name=d["name"],
            schema=d.get("schema", {}),
            risk=RiskLevel(d.get("risk", "low")),
            idempotent=d.get("idempotent", False),
            resource=d.get("resource", {}),
        )


# ── 状态图标 ────────────────────────────────────────────────────────────────

STATUS_ICON: dict[TaskStatus, str] = {
    TaskStatus.QUEUED: "⏳",
    TaskStatus.DISPATCHED: "📤",
    TaskStatus.RUNNING: "🔄",
    TaskStatus.INPUT_REQUIRED: "⏸️",
    TaskStatus.PAUSED: "⏸️",
    TaskStatus.COMPLETED: "✅",
    TaskStatus.FAILED: "❌",
    TaskStatus.CANCELED: "⚫",
    TaskStatus.TIMED_OUT: "⏰",
    TaskStatus.COMPENSATING: "🔧",
    TaskStatus.COMPENSATED: "🔧",
}
