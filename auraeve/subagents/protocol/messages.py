"""子体系统协议消息定义。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Any


def _span_id() -> str:
    return uuid.uuid4().hex[:16]


@dataclass
class TraceContext:
    trace_id: str = ""
    span_id: str = field(default_factory=_span_id)
    parent_span_id: str = ""


# ── 握手协议 ────────────────────────────────────────────────────────────────


@dataclass
class NodeConnectMsg:
    """远程子体 → 母体：握手请求。"""
    node_id: str
    token: str
    display_name: str = ""
    platform: str = ""
    version: str = "2.0.0"
    capabilities: list[dict] = field(default_factory=list)
    type: str = "node.connect"


@dataclass
class NodeConnectOkMsg:
    """母体 → 远程子体：握手成功。"""
    assigned_trace_id: str = ""
    pending_tasks: list[dict] = field(default_factory=list)
    type: str = "node.connect.ok"


@dataclass
class NodeConnectErrorMsg:
    """母体 → 远程子体：握手失败。"""
    reason: str = ""
    type: str = "node.connect.error"


# ── 任务协议 ────────────────────────────────────────────────────────────────


@dataclass
class TaskAssignMsg:
    """母体 → 子体：下发任务。"""
    task_id: str
    goal: str
    budget: dict = field(default_factory=dict)
    policy_profile: str = "default"
    depends_on: list[str] = field(default_factory=list)
    trace: TraceContext = field(default_factory=TraceContext)
    type: str = "task.assign"


@dataclass
class TaskProgressMsg:
    """子体 → 母体：进度上报。"""
    task_id: str
    step: int = 0
    message: str = ""
    tool_calls: int = 0
    tokens_used: int = 0
    trace: TraceContext = field(default_factory=TraceContext)
    type: str = "task.progress"


@dataclass
class TaskAlertMsg:
    """子体 → 母体：告警上报。"""
    task_id: str
    level: str = "warning"
    message: str = ""
    trace: TraceContext = field(default_factory=TraceContext)
    type: str = "task.alert"


@dataclass
class TaskDoneMsg:
    """子体 → 母体：任务完成。"""
    task_id: str
    success: bool = True
    result: str = ""
    artifacts: list[dict] = field(default_factory=list)
    memory_deltas: list[dict] = field(default_factory=list)
    experience: dict | None = None
    trace: TraceContext = field(default_factory=TraceContext)
    type: str = "task.done"


@dataclass
class TaskPauseMsg:
    """母体 → 子体：暂停任务。"""
    task_id: str
    reason: str = ""
    type: str = "task.pause"


@dataclass
class TaskResumeMsg:
    """母体 → 子体：恢复任务。"""
    task_id: str
    type: str = "task.resume"


@dataclass
class TaskCancelMsg:
    """母体 → 子体：取消任务。"""
    task_id: str
    reason: str = ""
    type: str = "task.cancel"


@dataclass
class TaskApprovalRequestMsg:
    """子体 → 母体：请求审批。"""
    task_id: str
    approval_id: str
    action_desc: str = ""
    risk_level: str = "high"
    context: dict = field(default_factory=dict)
    trace: TraceContext = field(default_factory=TraceContext)
    type: str = "task.approval_request"


@dataclass
class TaskApprovalDecideMsg:
    """母体 → 子体：审批结果。"""
    task_id: str
    approval_id: str
    decision: str = "reject"  # approve / reject / revise
    revised_params: dict = field(default_factory=dict)
    type: str = "task.approval_decide"


@dataclass
class TaskBudgetAdjustMsg:
    """母体 → 子体：动态调整预算。"""
    task_id: str
    budget: dict = field(default_factory=dict)
    type: str = "task.budget_adjust"


# ── 子体间通信 ──────────────────────────────────────────────────────────────


@dataclass
class PeerAuthorizeMsg:
    """母体 → 子体：授权子体间通信。"""
    peer_node_id: str
    task_id: str
    type: str = "peer.authorize"


@dataclass
class PeerMessageMsg:
    """子体 → 子体（经母体路由）：子体间消息。"""
    from_node_id: str
    to_node_id: str
    task_id: str
    content: str = ""
    trace: TraceContext = field(default_factory=TraceContext)
    type: str = "peer.message"


@dataclass
class PeerRequestMsg:
    """子体 → 母体：请求与指定子体通信。"""
    target_node_id: str
    task_id: str
    reason: str = ""
    type: str = "peer.request"


# ── 心跳 ────────────────────────────────────────────────────────────────────


@dataclass
class PingMsg:
    type: str = "ping"


@dataclass
class PongMsg:
    type: str = "pong"
