from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from auraeve.config.stores import save_json_file_atomic


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(value: str | None) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sanitize_task_list_id(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return "default"
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in text)
    safe = safe.strip("._")
    return safe or "default"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass(slots=True)
class TaskRecord:
    id: str
    subject: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    active_form: str | None = None
    owner: str | None = None
    blocks: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TaskRecord":
        return cls(
            id=str(payload["id"]),
            subject=str(payload["subject"]),
            description=str(payload.get("description") or ""),
            status=TaskStatus(str(payload.get("status") or TaskStatus.PENDING.value)),
            active_form=(
                str(payload["active_form"])
                if payload.get("active_form") not in {None, ""}
                else None
            ),
            owner=str(payload["owner"]) if payload.get("owner") not in {None, ""} else None,
            blocks=[str(item) for item in payload.get("blocks") or []],
            blocked_by=[str(item) for item in payload.get("blocked_by") or []],
            metadata=dict(payload.get("metadata") or {}),
            created_at=str(payload.get("created_at") or _utcnow()),
            updated_at=str(payload.get("updated_at") or payload.get("created_at") or _utcnow()),
        )


class TaskStore:
    def __init__(self, *, base_dir: Path, task_list_id: str) -> None:
        self._base_dir = Path(base_dir)
        self._task_list_id = _sanitize_task_list_id(task_list_id)
        self._dir = self._base_dir / self._task_list_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock_path = self._dir / ".lock"
        self._highwatermark_path = self._dir / ".highwatermark"

    @property
    def task_list_id(self) -> str:
        return self._task_list_id

    @property
    def directory(self) -> Path:
        return self._dir

    def create_task(
        self,
        *,
        subject: str,
        description: str,
        active_form: str | None = None,
        owner: str | None = None,
        status: TaskStatus = TaskStatus.PENDING,
        blocks: list[str] | None = None,
        blocked_by: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        completed_ttl_seconds: float = 5.0,
    ) -> TaskRecord:
        with self._locked():
            existing_tasks = self._prune_stale_unresolved_tasks_unlocked(
                self._read_tasks_unlocked()
            )
            if self._should_reset_completed_list(
                existing_tasks,
                completed_ttl_seconds=completed_ttl_seconds,
            ):
                self._reset_tasks_unlocked(existing_tasks)
            task_id = self._next_id()
            task = TaskRecord(
                id=task_id,
                subject=str(subject),
                description=str(description),
                status=status,
                active_form=active_form,
                owner=owner,
                blocks=[str(item) for item in blocks or []],
                blocked_by=[str(item) for item in blocked_by or []],
                metadata=dict(metadata or {}),
            )
            self._write_task(task)
            return task

    def get_task(self, task_id: str) -> TaskRecord | None:
        path = self._task_path(task_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return TaskRecord.from_payload(payload)

    def list_tasks(self) -> list[TaskRecord]:
        tasks = self._read_tasks_unlocked()
        tasks.sort(key=lambda item: int(item.id))
        return tasks

    def list_active_tasks(self, *, completed_ttl_seconds: float = 5.0) -> list[TaskRecord]:
        with self._locked():
            tasks = self._prune_stale_unresolved_tasks_unlocked(self._read_tasks_unlocked())
            tasks = [task for task in tasks if not task.metadata.get("_internal")]
            if not tasks:
                return []
            if not self._should_reset_completed_list(
                tasks,
                completed_ttl_seconds=completed_ttl_seconds,
            ):
                return tasks
            self._reset_tasks_unlocked(tasks)
            return []

    def update_task(
        self,
        task_id: str,
        *,
        subject: str | None = None,
        description: str | None = None,
        active_form: str | None = None,
        owner: str | None = None,
        status: TaskStatus | None = None,
        blocks: list[str] | None = None,
        blocked_by: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaskRecord:
        with self._locked():
            current = self.get_task(task_id)
            if current is None:
                raise KeyError(f"task {task_id} not found")
            if subject is not None:
                current.subject = str(subject)
            if description is not None:
                current.description = str(description)
            if active_form is not None:
                current.active_form = str(active_form) if str(active_form).strip() else None
            if owner is not None:
                current.owner = str(owner) if str(owner).strip() else None
            if status is not None:
                current.status = status
            if blocks is not None:
                current.blocks = [str(item) for item in blocks]
            if blocked_by is not None:
                current.blocked_by = [str(item) for item in blocked_by]
            if metadata is not None:
                current.metadata = dict(metadata)
            current.updated_at = _utcnow()
            self._write_task(current)
            return current

    def delete_task(self, task_id: str) -> None:
        with self._locked():
            self._task_path(task_id).unlink(missing_ok=True)

    def reset_tasks(self) -> None:
        with self._locked():
            self._reset_tasks_unlocked()

    def _task_path(self, task_id: str) -> Path:
        return self._dir / f"{task_id}.json"

    def _read_tasks_unlocked(self) -> list[TaskRecord]:
        tasks: list[TaskRecord] = []
        for path in self._dir.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            tasks.append(TaskRecord.from_payload(payload))
        return tasks

    def _reset_tasks_unlocked(self, tasks: list[TaskRecord] | None = None) -> None:
        highest = 0
        for task in tasks or self._read_tasks_unlocked():
            try:
                highest = max(highest, int(task.id))
            except ValueError:
                continue
        current_mark = 0
        if self._highwatermark_path.exists():
            try:
                current_mark = int(
                    self._highwatermark_path.read_text(encoding="utf-8").strip() or "0"
                )
            except Exception:
                current_mark = 0
        self._highwatermark_path.write_text(
            str(max(highest, current_mark)),
            encoding="utf-8",
        )
        for path in self._dir.glob("*.json"):
            path.unlink(missing_ok=True)

    def _should_reset_completed_list(
        self,
        tasks: list[TaskRecord],
        *,
        completed_ttl_seconds: float,
    ) -> bool:
        if not tasks:
            return False
        if any(task.status is not TaskStatus.COMPLETED for task in tasks):
            return False
        latest_update = max(_parse_timestamp(task.updated_at) for task in tasks)
        return datetime.now(timezone.utc) - latest_update >= timedelta(
            seconds=completed_ttl_seconds
        )

    def _prune_stale_unresolved_tasks_unlocked(
        self,
        tasks: list[TaskRecord],
        *,
        stale_after_seconds: float = 24 * 60 * 60,
    ) -> list[TaskRecord]:
        if len(tasks) < 2:
            return tasks
        latest_update = max(_parse_timestamp(task.updated_at) for task in tasks)
        threshold = timedelta(seconds=stale_after_seconds)
        stale_ids = {
            task.id
            for task in tasks
            if task.status is not TaskStatus.COMPLETED
            and latest_update - _parse_timestamp(task.updated_at) >= threshold
        }
        if not stale_ids:
            return tasks
        for task_id in stale_ids:
            self._task_path(task_id).unlink(missing_ok=True)
        return [task for task in tasks if task.id not in stale_ids]

    def _write_task(self, task: TaskRecord) -> None:
        save_json_file_atomic(self._task_path(task.id), task.to_payload())

    def _next_id(self) -> str:
        current = 0
        if self._highwatermark_path.exists():
            try:
                current = int(self._highwatermark_path.read_text(encoding="utf-8").strip() or "0")
            except Exception:
                current = 0
        current += 1
        self._highwatermark_path.write_text(str(current), encoding="utf-8")
        return str(current)

    @contextmanager
    def _locked(self):
        self._dir.mkdir(parents=True, exist_ok=True)
        handle = None
        started = time.time()
        while True:
            try:
                fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                handle = fd
                break
            except FileExistsError:
                if time.time() - started > 5:
                    raise TimeoutError(f"could not acquire task lock for {self._dir}")
                time.sleep(0.05)
        try:
            yield
        finally:
            if handle is not None:
                os.close(handle)
            self._lock_path.unlink(missing_ok=True)
