"""SQLite 持久化仓库。"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .models import (
    Approval, ApprovalStatus, CapabilityScore, DeltaType, MemoryDelta,
    MergeStatus, NodeSession, RiskLevel, Task, TaskArtifact, TaskBudget,
    TaskEvent, TaskStatus,
)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    assigned_node_id TEXT DEFAULT '',
    priority INTEGER DEFAULT 5,
    status TEXT NOT NULL,
    depends_on TEXT DEFAULT '[]',
    budget TEXT DEFAULT '{}',
    policy_profile TEXT DEFAULT 'default',
    result TEXT DEFAULT '',
    compensate_action TEXT,
    trace_id TEXT NOT NULL,
    origin_channel TEXT DEFAULT '',
    origin_chat_id TEXT DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS task_events (
    task_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT DEFAULT '{}',
    trace_id TEXT DEFAULT '',
    span_id TEXT DEFAULT '',
    parent_span_id TEXT DEFAULT '',
    created_at REAL NOT NULL,
    PRIMARY KEY (task_id, seq)
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    action_desc TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    decided_by TEXT DEFAULT '',
    decided_at REAL DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS task_artifacts (
    artifact_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    name TEXT NOT NULL,
    content_type TEXT DEFAULT 'text/plain',
    data BLOB,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS node_sessions (
    node_id TEXT PRIMARY KEY,
    display_name TEXT DEFAULT '',
    platform TEXT DEFAULT '',
    capabilities TEXT DEFAULT '[]',
    connected_at REAL DEFAULT 0,
    disconnected_at REAL DEFAULT 0,
    is_online INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS memory_deltas (
    delta_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    delta_type TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    merge_status TEXT DEFAULT 'pending',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS node_capability_scores (
    node_id TEXT NOT NULL,
    capability_domain TEXT NOT NULL,
    success_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    avg_duration_s REAL DEFAULT 0,
    last_updated REAL,
    PRIMARY KEY (node_id, capability_domain)
);
"""


class SubagentDB:
    """线程安全的 SQLite 子体数据仓库。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._local = threading.local()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA_SQL)
        conn.commit()

    # ── Task CRUD ───────────────────────────────────────────────────────────

    def save_task(self, task: Task) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO tasks
               (task_id, goal, assigned_node_id, priority, status, depends_on,
                budget, policy_profile, result, compensate_action, trace_id,
                origin_channel, origin_chat_id, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                task.task_id, task.goal, task.assigned_node_id, task.priority,
                task.status.value, json.dumps(task.depends_on),
                json.dumps(task.budget.to_dict()), task.policy_profile,
                task.result, task.compensate_action, task.trace_id,
                task.origin_channel, task.origin_chat_id,
                task.created_at, task.updated_at,
            ),
        )
        conn.commit()

    def get_task(self, task_id: str) -> Task | None:
        row = self._get_conn().execute(
            "SELECT * FROM tasks WHERE task_id=?", (task_id,)
        ).fetchone()
        return self._row_to_task(row) if row else None

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        node_id: str | None = None,
        limit: int = 100,
    ) -> list[Task]:
        sql = "SELECT * FROM tasks WHERE 1=1"
        params: list[Any] = []
        if status:
            sql += " AND status=?"
            params.append(status.value)
        if node_id:
            sql += " AND assigned_node_id=?"
            params.append(node_id)
        sql += " ORDER BY priority DESC, created_at ASC LIMIT ?"
        params.append(limit)
        rows = self._get_conn().execute(sql, params).fetchall()
        return [self._row_to_task(r) for r in rows]

    def update_task_status(self, task_id: str, status: TaskStatus) -> None:
        now = time.time()
        self._get_conn().execute(
            "UPDATE tasks SET status=?, updated_at=? WHERE task_id=?",
            (status.value, now, task_id),
        )
        self._get_conn().commit()

    def assign_task(self, task_id: str, node_id: str) -> None:
        now = time.time()
        conn = self._get_conn()
        conn.execute(
            "UPDATE tasks SET assigned_node_id=?, status=?, updated_at=? WHERE task_id=?",
            (node_id, TaskStatus.DISPATCHED.value, now, task_id),
        )
        conn.commit()

    def get_running_count(self, node_id: str | None = None) -> int:
        if node_id:
            row = self._get_conn().execute(
                "SELECT COUNT(*) FROM tasks WHERE status IN ('dispatched','running','input_required') AND assigned_node_id=?",
                (node_id,),
            ).fetchone()
        else:
            row = self._get_conn().execute(
                "SELECT COUNT(*) FROM tasks WHERE status IN ('dispatched','running','input_required')",
            ).fetchone()
        return row[0] if row else 0

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        return Task(
            task_id=row["task_id"],
            goal=row["goal"],
            assigned_node_id=row["assigned_node_id"] or "",
            priority=row["priority"],
            status=TaskStatus(row["status"]),
            depends_on=json.loads(row["depends_on"] or "[]"),
            budget=TaskBudget.from_dict(json.loads(row["budget"] or "{}")),
            policy_profile=row["policy_profile"] or "default",
            result=row["result"] or "",
            compensate_action=row["compensate_action"],
            trace_id=row["trace_id"],
            origin_channel=row["origin_channel"] or "",
            origin_chat_id=row["origin_chat_id"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ── TaskEvent ───────────────────────────────────────────────────────────

    def append_event(self, event: TaskEvent) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR IGNORE INTO task_events
               (task_id, seq, event_type, payload, trace_id, span_id, parent_span_id, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                event.task_id, event.seq, event.event_type,
                json.dumps(event.payload), event.trace_id,
                event.span_id, event.parent_span_id, event.created_at,
            ),
        )
        conn.commit()

    def get_next_seq(self, task_id: str) -> int:
        row = self._get_conn().execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM task_events WHERE task_id=?",
            (task_id,),
        ).fetchone()
        return row[0] if row else 1

    def get_events(self, task_id: str) -> list[TaskEvent]:
        rows = self._get_conn().execute(
            "SELECT * FROM task_events WHERE task_id=? ORDER BY seq", (task_id,)
        ).fetchall()
        return [
            TaskEvent(
                task_id=r["task_id"], seq=r["seq"], event_type=r["event_type"],
                payload=json.loads(r["payload"] or "{}"),
                trace_id=r["trace_id"] or "", span_id=r["span_id"] or "",
                parent_span_id=r["parent_span_id"] or "",
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # ── Approval ────────────────────────────────────────────────────────────

    def save_approval(self, approval: Approval) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO approvals
               (approval_id, task_id, action_desc, risk_level, status, decided_by, decided_at, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                approval.approval_id, approval.task_id, approval.action_desc,
                approval.risk_level.value, approval.status.value,
                approval.decided_by, approval.decided_at, approval.created_at,
            ),
        )
        conn.commit()

    def get_pending_approval(self, task_id: str) -> Approval | None:
        row = self._get_conn().execute(
            "SELECT * FROM approvals WHERE task_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if not row:
            return None
        return Approval(
            approval_id=row["approval_id"], task_id=row["task_id"],
            action_desc=row["action_desc"],
            risk_level=RiskLevel(row["risk_level"]),
            status=ApprovalStatus(row["status"]),
            decided_by=row["decided_by"] or "",
            decided_at=row["decided_at"],
            created_at=row["created_at"],
        )

    def decide_approval(self, approval_id: str, status: ApprovalStatus, decided_by: str = "") -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE approvals SET status=?, decided_by=?, decided_at=? WHERE approval_id=?",
            (status.value, decided_by, time.time(), approval_id),
        )
        conn.commit()

    # ── Artifact ────────────────────────────────────────────────────────────

    def save_artifact(self, artifact: TaskArtifact) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO task_artifacts
               (artifact_id, task_id, name, content_type, data, created_at)
               VALUES (?,?,?,?,?,?)""",
            (artifact.artifact_id, artifact.task_id, artifact.name,
             artifact.content_type, artifact.data, artifact.created_at),
        )
        conn.commit()

    # ── NodeSession ─────────────────────────────────────────────────────────

    def upsert_node(self, node: NodeSession) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO node_sessions
               (node_id, display_name, platform, capabilities, connected_at, disconnected_at, is_online)
               VALUES (?,?,?,?,?,?,?)""",
            (
                node.node_id, node.display_name, node.platform,
                json.dumps([c if isinstance(c, dict) else c for c in node.capabilities]),
                node.connected_at, node.disconnected_at,
                1 if node.is_online else 0,
            ),
        )
        conn.commit()

    def set_node_online(self, node_id: str, online: bool) -> None:
        conn = self._get_conn()
        now = time.time()
        if online:
            conn.execute(
                "UPDATE node_sessions SET is_online=1, connected_at=? WHERE node_id=?",
                (now, node_id),
            )
        else:
            conn.execute(
                "UPDATE node_sessions SET is_online=0, disconnected_at=? WHERE node_id=?",
                (now, node_id),
            )
        conn.commit()

    def get_online_nodes(self) -> list[NodeSession]:
        rows = self._get_conn().execute(
            "SELECT * FROM node_sessions WHERE is_online=1"
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def get_node(self, node_id: str) -> NodeSession | None:
        row = self._get_conn().execute(
            "SELECT * FROM node_sessions WHERE node_id=?", (node_id,)
        ).fetchone()
        return self._row_to_node(row) if row else None

    def _row_to_node(self, row: sqlite3.Row) -> NodeSession:
        return NodeSession(
            node_id=row["node_id"],
            display_name=row["display_name"] or "",
            platform=row["platform"] or "",
            capabilities=json.loads(row["capabilities"] or "[]"),
            connected_at=row["connected_at"],
            disconnected_at=row["disconnected_at"],
            is_online=bool(row["is_online"]),
        )

    # ── MemoryDelta ─────────────────────────────────────────────────────────

    def save_memory_delta(self, delta: MemoryDelta) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO memory_deltas
               (delta_id, task_id, node_id, delta_type, content, confidence, merge_status, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                delta.delta_id, delta.task_id, delta.node_id,
                delta.delta_type.value, delta.content, delta.confidence,
                delta.merge_status.value, delta.created_at,
            ),
        )
        conn.commit()

    def get_pending_deltas(self, limit: int = 50) -> list[MemoryDelta]:
        rows = self._get_conn().execute(
            "SELECT * FROM memory_deltas WHERE merge_status='pending' ORDER BY created_at LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            MemoryDelta(
                delta_id=r["delta_id"], task_id=r["task_id"], node_id=r["node_id"],
                delta_type=DeltaType(r["delta_type"]), content=r["content"],
                confidence=r["confidence"], merge_status=MergeStatus(r["merge_status"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def update_delta_status(self, delta_id: str, status: MergeStatus) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE memory_deltas SET merge_status=? WHERE delta_id=?",
            (status.value, delta_id),
        )
        conn.commit()

    # ── CapabilityScore ─────────────────────────────────────────────────────

    def upsert_capability_score(self, score: CapabilityScore) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO node_capability_scores
               (node_id, capability_domain, success_count, fail_count, avg_duration_s, last_updated)
               VALUES (?,?,?,?,?,?)""",
            (
                score.node_id, score.capability_domain,
                score.success_count, score.fail_count,
                score.avg_duration_s, score.last_updated,
            ),
        )
        conn.commit()

    def get_capability_scores(self, node_id: str) -> list[CapabilityScore]:
        rows = self._get_conn().execute(
            "SELECT * FROM node_capability_scores WHERE node_id=?", (node_id,)
        ).fetchall()
        return [
            CapabilityScore(
                node_id=r["node_id"], capability_domain=r["capability_domain"],
                success_count=r["success_count"], fail_count=r["fail_count"],
                avg_duration_s=r["avg_duration_s"], last_updated=r["last_updated"] or 0,
            )
            for r in rows
        ]

    def record_task_outcome(
        self, node_id: str, domain: str, success: bool, duration_s: float
    ) -> None:
        existing = self._get_conn().execute(
            "SELECT * FROM node_capability_scores WHERE node_id=? AND capability_domain=?",
            (node_id, domain),
        ).fetchone()
        now = time.time()
        if existing:
            sc = existing["success_count"] + (1 if success else 0)
            fc = existing["fail_count"] + (0 if success else 1)
            total = sc + fc
            old_avg = existing["avg_duration_s"] or 0
            new_avg = ((old_avg * (total - 1)) + duration_s) / total if total > 0 else duration_s
            self._get_conn().execute(
                """UPDATE node_capability_scores
                   SET success_count=?, fail_count=?, avg_duration_s=?, last_updated=?
                   WHERE node_id=? AND capability_domain=?""",
                (sc, fc, new_avg, now, node_id, domain),
            )
        else:
            self._get_conn().execute(
                """INSERT INTO node_capability_scores
                   (node_id, capability_domain, success_count, fail_count, avg_duration_s, last_updated)
                   VALUES (?,?,?,?,?,?)""",
                (node_id, domain, 1 if success else 0, 0 if success else 1, duration_s, now),
            )
        self._get_conn().commit()
