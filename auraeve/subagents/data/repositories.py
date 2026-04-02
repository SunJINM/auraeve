"""子智能体数据存储。

线程安全的 SQLite 持久化，只保留 Task 的 CRUD。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .models import Task, TaskBudget, TaskStatus


class SubagentStore:
    """子智能体任务存储。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._local = threading.local()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_schema(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id          TEXT PRIMARY KEY,
                goal             TEXT NOT NULL,
                agent_type       TEXT NOT NULL DEFAULT 'general-purpose',
                status           TEXT NOT NULL DEFAULT 'queued',
                priority         INTEGER NOT NULL DEFAULT 5,
                budget_json      TEXT NOT NULL DEFAULT '{}',
                role_prompt      TEXT NOT NULL DEFAULT '',
                result           TEXT NOT NULL DEFAULT '',
                origin_channel   TEXT NOT NULL DEFAULT '',
                origin_chat_id   TEXT NOT NULL DEFAULT '',
                spawn_tool_call_id TEXT NOT NULL DEFAULT '',
                run_in_background INTEGER NOT NULL DEFAULT 1,
                worktree_path    TEXT NOT NULL DEFAULT '',
                worktree_branch  TEXT NOT NULL DEFAULT '',
                created_at       REAL NOT NULL,
                completed_at     REAL NOT NULL DEFAULT 0.0
            )
        """)
        conn.commit()

    def save_task(self, task: Task) -> None:
        conn = self._get_conn()
        budget_json = json.dumps({
            "max_steps": task.budget.max_steps,
            "max_duration_s": task.budget.max_duration_s,
            "max_tool_calls": task.budget.max_tool_calls,
        })
        conn.execute(
            """INSERT OR REPLACE INTO tasks
               (task_id, goal, agent_type, status, priority, budget_json,
                role_prompt, result, origin_channel, origin_chat_id,
                spawn_tool_call_id, run_in_background, worktree_path,
                worktree_branch, created_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.task_id, task.goal, task.agent_type, task.status.value,
                task.priority, budget_json, task.role_prompt, task.result,
                task.origin_channel, task.origin_chat_id,
                task.spawn_tool_call_id, int(task.run_in_background),
                task.worktree_path, task.worktree_branch,
                task.created_at, task.completed_at,
            ),
        )
        conn.commit()

    def get_task(self, task_id: str) -> Task | None:
        row = self._get_conn().execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[Task]:
        if status is not None:
            rows = self._get_conn().execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status.value, limit),
            ).fetchall()
        else:
            rows = self._get_conn().execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def update_task_status(self, task_id: str, status: TaskStatus) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE tasks SET status = ? WHERE task_id = ?",
            (status.value, task_id),
        )
        conn.commit()

    def complete_task(
        self,
        task_id: str,
        result: str = "",
        completed_at: float = 0.0,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE tasks SET status = ?, result = ?, completed_at = ? WHERE task_id = ?",
            (TaskStatus.COMPLETED.value, result, completed_at, task_id),
        )
        conn.commit()

    def get_running_count(self) -> int:
        row = self._get_conn().execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status = ?",
            (TaskStatus.RUNNING.value,),
        ).fetchone()
        return row["cnt"] if row else 0

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        budget_data = json.loads(row["budget_json"]) if row["budget_json"] else {}
        budget = TaskBudget(
            max_steps=budget_data.get("max_steps", 50),
            max_duration_s=budget_data.get("max_duration_s", 600),
            max_tool_calls=budget_data.get("max_tool_calls", 100),
        )
        return Task(
            task_id=row["task_id"],
            goal=row["goal"],
            agent_type=row["agent_type"],
            status=TaskStatus(row["status"]),
            priority=row["priority"],
            budget=budget,
            role_prompt=row["role_prompt"],
            result=row["result"],
            origin_channel=row["origin_channel"],
            origin_chat_id=row["origin_chat_id"],
            spawn_tool_call_id=row["spawn_tool_call_id"],
            run_in_background=bool(row["run_in_background"]),
            worktree_path=row["worktree_path"],
            worktree_branch=row["worktree_branch"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )
