from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from auraeve.config.paths import resolve_state_dir

_LEVEL_ORDER = {
    "trace": 10,
    "debug": 20,
    "info": 30,
    "warn": 40,
    "warning": 40,
    "error": 50,
    "fatal": 60,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds")


@dataclass(slots=True)
class ObservabilitySettings:
    enabled: bool = True
    level: str = "info"
    dir_path: Path | None = None
    segment_max_mb: int = 64
    retention_days: int = 14
    max_total_gb: int = 5
    retention_check_every: int = 200
    stream_queue_size: int = 2000
    search_default_limit: int = 200
    search_max_limit: int = 5000

    @property
    def segment_max_bytes(self) -> int:
        return max(1, self.segment_max_mb) * 1024 * 1024

    @property
    def max_total_bytes(self) -> int:
        return max(1, self.max_total_gb) * 1024 * 1024 * 1024


@dataclass(slots=True)
class _Subscriber:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[dict[str, Any]]
    levels: set[str] | None
    subsystems: set[str] | None
    text: str


class ObservabilityManager:
    def __init__(self, settings: ObservabilitySettings | None = None) -> None:
        self._settings = settings or ObservabilitySettings()
        base_dir = self._settings.dir_path or (resolve_state_dir() / "logs")
        self._root = base_dir.resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._db_path = self._root / "index.db"
        self._lock = threading.Lock()
        self._subscribers: dict[str, _Subscriber] = {}
        self._min_level = self._normalize_level(self._settings.level)
        self._emit_counter = 0

        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    def _normalize_level(self, level: str) -> str:
        val = str(level or "info").strip().lower()
        if val == "warning":
            return "warn"
        return val if val in _LEVEL_ORDER else "info"

    def _is_level_enabled(self, level: str) -> bool:
        return _LEVEL_ORDER.get(self._normalize_level(level), 30) >= _LEVEL_ORDER.get(self._min_level, 30)

    def _init_db(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS log_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    level TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    subsystem TEXT NOT NULL,
                    message TEXT NOT NULL,
                    session_key TEXT,
                    run_id TEXT,
                    channel TEXT,
                    attrs_json TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_offset INTEGER NOT NULL
                )
                """
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_log_ts_ms ON log_events(ts_ms)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_log_level_ts ON log_events(level, ts_ms)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_log_subsystem_ts ON log_events(subsystem, ts_ms)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_log_session_ts ON log_events(session_key, ts_ms)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_log_run_ts ON log_events(run_id, ts_ms)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_log_channel_ts ON log_events(channel, ts_ms)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_log_kind_ts ON log_events(kind, ts_ms)")

    def _build_rel_file_path(self, dt: datetime, part: int) -> Path:
        return Path(f"{dt:%Y/%m/%d}/auraeve-{dt:%Y%m%d-%H}-part{part:02d}.jsonl")

    def _resolve_active_file(self, dt: datetime) -> Path:
        day_dir = self._root / f"{dt:%Y/%m/%d}"
        day_dir.mkdir(parents=True, exist_ok=True)
        part = 1
        while True:
            rel = self._build_rel_file_path(dt, part)
            path = self._root / rel
            if not path.exists():
                return path
            try:
                if path.stat().st_size < self._settings.segment_max_bytes:
                    return path
            except OSError:
                return path
            part += 1

    def _append_line(self, line: str, dt: datetime) -> tuple[str, int]:
        path = self._resolve_active_file(dt)
        payload = (line + "\n").encode("utf-8")
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        with path.open("ab") as fp:
            fp.write(payload)
        return str(path), size

    def emit(
        self,
        *,
        level: str,
        subsystem: str,
        message: str,
        kind: str = "log",
        attrs: dict[str, Any] | None = None,
        session_key: str | None = None,
        run_id: str | None = None,
        channel: str | None = None,
    ) -> dict[str, Any] | None:
        if not self._settings.enabled:
            return None
        normalized_level = self._normalize_level(level)
        if not self._is_level_enabled(normalized_level):
            return None

        dt = _utc_now()
        event = {
            "eventId": str(uuid.uuid4()),
            "ts": _iso(dt),
            "tsMs": int(dt.timestamp() * 1000),
            "level": normalized_level,
            "kind": str(kind or "log"),
            "subsystem": str(subsystem or "general"),
            "message": str(message or ""),
            "sessionKey": session_key,
            "runId": run_id,
            "channel": channel,
            "attrs": attrs or {},
        }
        line = json.dumps(event, ensure_ascii=False)

        with self._lock:
            file_path, file_offset = self._append_line(line, dt)
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO log_events (
                        event_id, ts, ts_ms, level, kind, subsystem, message,
                        session_key, run_id, channel, attrs_json, file_path, file_offset
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["eventId"],
                        event["ts"],
                        event["tsMs"],
                        event["level"],
                        event["kind"],
                        event["subsystem"],
                        event["message"],
                        event["sessionKey"],
                        event["runId"],
                        event["channel"],
                        json.dumps(event["attrs"], ensure_ascii=False),
                        file_path,
                        file_offset,
                    ),
                )
            self._emit_counter += 1
            if self._emit_counter >= max(1, self._settings.retention_check_every):
                self._emit_counter = 0
                self._apply_retention_locked()

        self._publish(event)
        return event

    def emit_audit(self, subsystem: str, action: str, attrs: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return self.emit(
            level="info",
            kind="audit",
            subsystem=subsystem,
            message=action,
            attrs=attrs or {},
        )

    def _matches_subscriber(self, sub: _Subscriber, event: dict[str, Any]) -> bool:
        if sub.levels and str(event.get("level") or "") not in sub.levels:
            return False
        subsystem = str(event.get("subsystem") or "")
        if sub.subsystems and subsystem not in sub.subsystems:
            return False
        if sub.text:
            hay = json.dumps(event, ensure_ascii=False).lower()
            if sub.text not in hay:
                return False
        return True

    def _publish(self, event: dict[str, Any]) -> None:
        stale: list[str] = []
        for sub_id, sub in list(self._subscribers.items()):
            if not self._matches_subscriber(sub, event):
                continue

            def _enqueue(target: _Subscriber = sub) -> None:
                if target.queue.full():
                    try:
                        target.queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                try:
                    target.queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

            try:
                sub.loop.call_soon_threadsafe(_enqueue)
            except RuntimeError:
                stale.append(sub_id)
        for sub_id in stale:
            self._subscribers.pop(sub_id, None)

    def subscribe(
        self,
        *,
        levels: list[str] | None = None,
        subsystems: list[str] | None = None,
        text: str | None = None,
    ) -> tuple[str, asyncio.Queue[dict[str, Any]]]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._settings.stream_queue_size)
        sub_id = str(uuid.uuid4())
        normalized_levels = {
            self._normalize_level(level)
            for level in (levels or [])
            if self._normalize_level(level) in _LEVEL_ORDER
        }
        normalized_subsystems = {item.strip() for item in (subsystems or []) if item.strip()}
        self._subscribers[sub_id] = _Subscriber(
            loop=loop,
            queue=queue,
            levels=normalized_levels or None,
            subsystems=normalized_subsystems or None,
            text=(text or "").strip().lower(),
        )
        return sub_id, queue

    def unsubscribe(self, subscription_id: str) -> None:
        self._subscribers.pop(subscription_id, None)

    def current_log_file(self) -> str:
        dt = _utc_now()
        return str(self._resolve_active_file(dt))

    def tail(self, cursor: int | None = None, limit: int = 500, max_bytes: int = 250_000) -> dict[str, Any]:
        limit = max(1, min(limit, self._settings.search_max_limit))
        max_bytes = max(1, min(max_bytes, 1_000_000))
        file = Path(self.current_log_file())
        if not file.exists():
            return {
                "file": str(file),
                "cursor": 0,
                "size": 0,
                "events": [],
                "truncated": False,
                "reset": False,
            }
        size = file.stat().st_size
        start = 0
        reset = False
        truncated = False

        if cursor is None:
            start = max(0, size - max_bytes)
            truncated = start > 0
        else:
            start = max(0, int(cursor))
            if start > size:
                start = max(0, size - max_bytes)
                reset = True
                truncated = start > 0
            elif size - start > max_bytes:
                start = max(0, size - max_bytes)
                reset = True
                truncated = True

        if size == 0 or start >= size:
            return {
                "file": str(file),
                "cursor": size,
                "size": size,
                "events": [],
                "truncated": truncated,
                "reset": reset,
            }

        with file.open("rb") as fp:
            fp.seek(start)
            payload = fp.read(size - start)
        text = payload.decode("utf-8", errors="replace")
        lines = text.splitlines()
        events: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({"kind": "raw", "message": line})

        return {
            "file": str(file),
            "cursor": size,
            "size": size,
            "events": events,
            "truncated": truncated,
            "reset": reset,
        }

    def search(
        self,
        *,
        levels: list[str] | None = None,
        subsystems: list[str] | None = None,
        kinds: list[str] | None = None,
        text: str | None = None,
        session_key: str | None = None,
        run_id: str | None = None,
        channel: str | None = None,
        ts_from_ms: int | None = None,
        ts_to_ms: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict[str, Any]:
        query_parts = ["SELECT * FROM log_events WHERE 1=1"]
        count_parts = ["SELECT COUNT(*) FROM log_events WHERE 1=1"]
        args: list[Any] = []
        count_args: list[Any] = []

        def _where(fragment: str, value: Any) -> None:
            query_parts.append(fragment)
            count_parts.append(fragment)
            args.append(value)
            count_args.append(value)

        normalized_levels = [self._normalize_level(item) for item in (levels or []) if item]
        if normalized_levels:
            placeholders = ",".join("?" for _ in normalized_levels)
            query_parts.append(f"AND level IN ({placeholders})")
            count_parts.append(f"AND level IN ({placeholders})")
            args.extend(normalized_levels)
            count_args.extend(normalized_levels)

        normalized_subsystems = [item.strip() for item in (subsystems or []) if item and item.strip()]
        if normalized_subsystems:
            placeholders = ",".join("?" for _ in normalized_subsystems)
            query_parts.append(f"AND subsystem IN ({placeholders})")
            count_parts.append(f"AND subsystem IN ({placeholders})")
            args.extend(normalized_subsystems)
            count_args.extend(normalized_subsystems)

        normalized_kinds = [item.strip() for item in (kinds or []) if item and item.strip()]
        if normalized_kinds:
            placeholders = ",".join("?" for _ in normalized_kinds)
            query_parts.append(f"AND kind IN ({placeholders})")
            count_parts.append(f"AND kind IN ({placeholders})")
            args.extend(normalized_kinds)
            count_args.extend(normalized_kinds)

        if session_key:
            _where("AND session_key = ?", session_key)
        if run_id:
            _where("AND run_id = ?", run_id)
        if channel:
            _where("AND channel = ?", channel)
        if ts_from_ms is not None:
            _where("AND ts_ms >= ?", int(ts_from_ms))
        if ts_to_ms is not None:
            _where("AND ts_ms <= ?", int(ts_to_ms))
        if text:
            like = f"%{text.strip()}%"
            query_parts.append("AND (message LIKE ? OR attrs_json LIKE ?)")
            count_parts.append("AND (message LIKE ? OR attrs_json LIKE ?)")
            args.extend([like, like])
            count_args.extend([like, like])

        resolved_limit = limit if isinstance(limit, int) and limit > 0 else self._settings.search_default_limit
        resolved_limit = max(1, min(resolved_limit, self._settings.search_max_limit))
        resolved_offset = max(0, int(offset))

        query_parts.append("ORDER BY ts_ms DESC, id DESC LIMIT ? OFFSET ?")
        args.extend([resolved_limit, resolved_offset])

        rows = self._conn.execute(" ".join(query_parts), args).fetchall()
        total = int(self._conn.execute(" ".join(count_parts), count_args).fetchone()[0])

        events = [self._row_to_event(row) for row in rows]

        return {
            "total": total,
            "limit": resolved_limit,
            "offset": resolved_offset,
            "events": events,
            "hasMore": resolved_offset + len(events) < total,
        }

    def stats(self, *, ts_from_ms: int | None = None, ts_to_ms: int | None = None) -> dict[str, Any]:
        where = ["1=1"]
        args: list[Any] = []
        if ts_from_ms is not None:
            where.append("ts_ms >= ?")
            args.append(int(ts_from_ms))
        if ts_to_ms is not None:
            where.append("ts_ms <= ?")
            args.append(int(ts_to_ms))
        where_sql = " AND ".join(where)

        total = int(self._conn.execute(f"SELECT COUNT(*) FROM log_events WHERE {where_sql}", args).fetchone()[0])

        levels = defaultdict(int)
        for row in self._conn.execute(
            f"SELECT level, COUNT(*) as cnt FROM log_events WHERE {where_sql} GROUP BY level",
            args,
        ):
            levels[str(row["level"])] = int(row["cnt"])

        subsystems = []
        for row in self._conn.execute(
            f"SELECT subsystem, COUNT(*) as cnt FROM log_events WHERE {where_sql} GROUP BY subsystem ORDER BY cnt DESC LIMIT 20",
            args,
        ):
            subsystems.append({"subsystem": row["subsystem"], "count": int(row["cnt"])})

        kinds = []
        by_kind = defaultdict(int)
        for row in self._conn.execute(
            f"SELECT kind, COUNT(*) as cnt FROM log_events WHERE {where_sql} GROUP BY kind ORDER BY cnt DESC LIMIT 20",
            args,
        ):
            kind_name = str(row["kind"] or "")
            cnt = int(row["cnt"])
            by_kind[kind_name] = cnt
            kinds.append({"kind": kind_name, "count": cnt})

        channels = []
        for row in self._conn.execute(
            f"SELECT channel, COUNT(*) as cnt FROM log_events WHERE {where_sql} AND channel IS NOT NULL AND channel != '' GROUP BY channel ORDER BY cnt DESC LIMIT 20",
            args,
        ):
            channels.append({"channel": str(row["channel"] or ""), "count": int(row["cnt"])})

        recent_errors = []
        for row in self._conn.execute(
            f"""
            SELECT * FROM log_events
            WHERE {where_sql} AND level IN ('error', 'fatal')
            ORDER BY ts_ms DESC, id DESC
            LIMIT 15
            """,
            args,
        ):
            recent_errors.append(self._row_to_event(row))

        return {
            "total": total,
            "byLevel": dict(levels),
            "byKind": dict(by_kind),
            "topSubsystems": subsystems,
            "topKinds": kinds,
            "topChannels": channels,
            "recentErrors": recent_errors,
        }

    def context(self, *, event_id: str, before: int = 20, after: int = 20) -> dict[str, Any]:
        before = max(0, min(before, 200))
        after = max(0, min(after, 200))
        row = self._conn.execute(
            "SELECT id FROM log_events WHERE event_id = ? LIMIT 1",
            (event_id,),
        ).fetchone()
        if not row:
            return {"ok": False, "events": []}
        center_id = int(row["id"])
        prev_rows = self._conn.execute(
            "SELECT * FROM log_events WHERE id < ? ORDER BY id DESC LIMIT ?",
            (center_id, before),
        ).fetchall()
        center_rows = self._conn.execute(
            "SELECT * FROM log_events WHERE id = ?",
            (center_id,),
        ).fetchall()
        next_rows = self._conn.execute(
            "SELECT * FROM log_events WHERE id > ? ORDER BY id ASC LIMIT ?",
            (center_id, after),
        ).fetchall()
        rows = list(reversed(prev_rows)) + center_rows + list(next_rows)
        return {
            "ok": True,
            "events": [self._row_to_event(item) for item in rows],
        }

    def export_events(
        self,
        *,
        levels: list[str] | None = None,
        subsystems: list[str] | None = None,
        kinds: list[str] | None = None,
        text: str | None = None,
        session_key: str | None = None,
        run_id: str | None = None,
        channel: str | None = None,
        ts_from_ms: int | None = None,
        ts_to_ms: int | None = None,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        result = self.search(
            levels=levels,
            subsystems=subsystems,
            kinds=kinds,
            text=text,
            session_key=session_key,
            run_id=run_id,
            channel=channel,
            ts_from_ms=ts_from_ms,
            ts_to_ms=ts_to_ms,
            limit=max(1, min(limit, 10000)),
            offset=0,
        )
        events = result.get("events", [])
        if not isinstance(events, list):
            return []
        return events

    def _row_to_event(self, row: sqlite3.Row) -> dict[str, Any]:
        attrs_obj: dict[str, Any]
        try:
            attrs_obj = json.loads(row["attrs_json"]) if row["attrs_json"] else {}
        except json.JSONDecodeError:
            attrs_obj = {}
        return {
            "eventId": row["event_id"],
            "ts": row["ts"],
            "tsMs": row["ts_ms"],
            "level": row["level"],
            "kind": row["kind"],
            "subsystem": row["subsystem"],
            "message": row["message"],
            "sessionKey": row["session_key"],
            "runId": row["run_id"],
            "channel": row["channel"],
            "attrs": attrs_obj,
        }

    def _apply_retention_locked(self) -> None:
        cutoff_ms = int(_utc_now().timestamp() * 1000) - max(1, self._settings.retention_days) * 86400000
        with self._conn:
            self._conn.execute("DELETE FROM log_events WHERE ts_ms < ?", (cutoff_ms,))

        files: list[tuple[Path, int, float]] = []
        total_bytes = 0
        for path in self._root.rglob("*.jsonl"):
            try:
                stat = path.stat()
            except OSError:
                continue
            files.append((path, stat.st_size, stat.mtime))
            total_bytes += stat.st_size
        files.sort(key=lambda item: item[2])

        max_total = self._settings.max_total_bytes
        removed_files: list[str] = []
        while total_bytes > max_total and files:
            path, size, _mtime = files.pop(0)
            try:
                path.unlink(missing_ok=True)
                total_bytes -= size
                removed_files.append(str(path))
            except OSError:
                continue

        if removed_files:
            placeholders = ",".join("?" for _ in removed_files)
            with self._conn:
                self._conn.execute(
                    f"DELETE FROM log_events WHERE file_path IN ({placeholders})",
                    removed_files,
                )

    def close(self) -> None:
        self._conn.close()


_GLOBAL_MANAGER: ObservabilityManager | None = None


def _settings_from_payload(config: dict[str, Any] | None = None) -> ObservabilitySettings:
    payload = config or {}
    logging_cfg = payload.get("LOGGING") if isinstance(payload.get("LOGGING"), dict) else {}
    state_dir_override = os.environ.get("AURAEVE_STATE_DIR", "").strip()
    root = Path(state_dir_override).expanduser() / "logs" if state_dir_override else (resolve_state_dir() / "logs")
    return ObservabilitySettings(
        enabled=bool(logging_cfg.get("enabled", True)),
        level=str(logging_cfg.get("level") or "info"),
        dir_path=root,
        segment_max_mb=int(logging_cfg.get("segmentMaxMB", 64) or 64),
        retention_days=int(logging_cfg.get("retentionDays", 14) or 14),
        max_total_gb=int(logging_cfg.get("maxTotalGB", 5) or 5),
        retention_check_every=int(logging_cfg.get("retentionCheckEvery", 200) or 200),
        stream_queue_size=int(logging_cfg.get("stream", {}).get("queueSize", 2000) or 2000)
        if isinstance(logging_cfg.get("stream"), dict)
        else 2000,
        search_default_limit=int(logging_cfg.get("search", {}).get("defaultLimit", 200) or 200)
        if isinstance(logging_cfg.get("search"), dict)
        else 200,
        search_max_limit=int(logging_cfg.get("search", {}).get("maxLimit", 5000) or 5000)
        if isinstance(logging_cfg.get("search"), dict)
        else 5000,
    )


def init_observability(config: dict[str, Any] | None = None) -> ObservabilityManager:
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is not None:
        _GLOBAL_MANAGER.close()
    settings = _settings_from_payload(config)
    _GLOBAL_MANAGER = ObservabilityManager(settings)
    return _GLOBAL_MANAGER


def get_observability() -> ObservabilityManager:
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is None:
        _GLOBAL_MANAGER = ObservabilityManager(_settings_from_payload(None))
    return _GLOBAL_MANAGER
