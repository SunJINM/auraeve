from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from auraeve.agent.engines.vector.store import Embedder, SearchResult, VectorMemoryStore


_EVERGREEN_FILES = {"MEMORY.MD", "AGENTS.MD", "SOUL.MD", "USER.MD", "TOOLS.MD", "IDENTITY.MD"}


class MemoryManager:
    """
    Unified memory manager for search/read/status/sync.

    - event-driven dirty-file sync (mark_dirty + periodic fallback scan)
    - explicit read guard (only MEMORY.md / memory.md / memory/*.md)
    - optional sessions source indexing (jsonl -> normalized markdown)
    - search fallback to keyword-only mode when embedding is unavailable
    """

    def __init__(
        self,
        *,
        workspace: Path,
        store: "VectorMemoryStore",
        embedder: "Embedder",
        search_limit: int = 8,
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
        mmr_lambda: float = 0.7,
        half_life_days: float = 30.0,
        periodic_scan_seconds: int = 30,
        sessions_dir: Path | None = None,
        include_sessions: bool = False,
        sessions_max_messages: int = 400,
    ) -> None:
        self.workspace = workspace
        self.store = store
        self.embedder = embedder
        self.search_limit = max(1, int(search_limit))
        self.vector_weight = float(vector_weight)
        self.text_weight = float(text_weight)
        self.mmr_lambda = float(mmr_lambda)
        self.half_life_days = float(half_life_days)
        self.periodic_scan_seconds = max(10, int(periodic_scan_seconds))
        self.include_sessions = bool(include_sessions)
        self.sessions_max_messages = max(50, int(sessions_max_messages))

        self._memory_dir = self.workspace / "memory"
        self._sessions_dir = sessions_dir
        self._sync_lock = asyncio.Lock()
        self._dirty_files: set[str] = set()
        self._tracked_files: set[str] = set()
        self._running = False
        self._scan_task: asyncio.Task | None = None
        self._last_search_mode = "hybrid"
        self._last_error: str | None = None
        self._sync_failures = 0
        self._sync_runs = 0
        self._last_sync_reason = "bootstrap"
        self._last_sync_duration_ms = 0
        self._last_sync_updated_files = 0

    async def bootstrap(self) -> int:
        self._running = True
        indexed = await self.sync(reason="bootstrap", force=True)
        if self._scan_task is None:
            self._scan_task = asyncio.create_task(self._periodic_scan_loop())
        return indexed

    async def close(self) -> None:
        self._running = False
        if self._scan_task is not None:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None

    def mark_dirty(self, file_path: Path | str) -> None:
        p = Path(file_path)
        if not p.is_absolute():
            p = (self.workspace / p).resolve()
        if not self._is_allowed_memory_file(p):
            return
        self._dirty_files.add(str(p))

    def mark_all_dirty(self) -> None:
        for key in self._list_documents().keys():
            self._dirty_files.add(key)

    async def sync(self, *, reason: str = "manual", force: bool = False) -> int:
        async with self._sync_lock:
            started = time.perf_counter()
            current_docs = self._list_documents()
            if force:
                target_paths = set(current_docs.keys())
                deleted_paths = self._tracked_files - set(current_docs.keys())
            else:
                target_paths = set(self._dirty_files)
                deleted_paths = {p for p in target_paths if p not in current_docs}
                target_paths = {p for p in target_paths if p in current_docs}
                deleted_paths |= self._tracked_files - set(current_docs.keys())

            indexed_files = 0
            for key in sorted(target_paths):
                entry = current_docs[key]
                try:
                    if entry["kind"] == "file":
                        chunks = await self.store.index_file(
                            entry["path"],
                            entry["source"],
                            self.embedder,
                        )
                    else:
                        chunks = await self.store.index_content(
                            path_key=key,
                            source=entry["source"],
                            content=entry["content"],
                            mtime=entry["mtime"],
                            embedder=self.embedder,
                        )
                    if chunks > 0:
                        indexed_files += 1
                        logger.debug(f"  索引 {entry['label']}：{chunks} 个片段")
                except Exception as exc:  # noqa: BLE001
                    self._last_error = str(exc)
                    self._sync_failures += 1
                    logger.warning(f"  索引 {entry['label']} 失败：{exc}")

            for deleted in sorted(deleted_paths):
                try:
                    self.store.delete_file(deleted)
                except Exception as exc:  # noqa: BLE001
                    self._last_error = str(exc)
                    self._sync_failures += 1
                    logger.warning(f"  清理已删除记忆文件索引失败 {deleted}: {exc}")

            self._tracked_files = set(current_docs.keys())
            self._dirty_files.difference_update(target_paths | deleted_paths)
            self._sync_runs += 1
            self._last_sync_reason = reason
            self._last_sync_updated_files = indexed_files
            self._last_sync_duration_ms = int((time.perf_counter() - started) * 1000)
            if indexed_files > 0:
                logger.debug(f"记忆索引同步完成（reason={reason}，updated={indexed_files}）")
            return indexed_files

    async def search(
        self,
        *,
        query: str,
        max_results: int | None = None,
        min_score: float = 0.05,
    ) -> list["SearchResult"]:
        cleaned = (query or "").strip()
        if not cleaned:
            return []
        # Best-effort background sync when files are dirty.
        if self._dirty_files:
            asyncio.create_task(self.sync(reason="search", force=False))

        limit = min(max(1, int(max_results or self.search_limit)), 20)

        try:
            query_vec = await self.embedder.embed(cleaned)
            self._last_search_mode = "hybrid"
            results = self.store.hybrid_search(
                query=cleaned,
                query_vec=query_vec,
                model=self.embedder.model,
                limit=limit,
                vector_weight=self.vector_weight,
                text_weight=self.text_weight,
                half_life_days=self.half_life_days,
                mmr_lambda=self.mmr_lambda,
            )
            return [r for r in results if r.score >= float(min_score)]
        except Exception as exc:  # noqa: BLE001
            # Fallback: keyword-only search
            self._last_error = str(exc)
            self._last_search_mode = "fts-only"
            keyword = self.store.search_keyword(cleaned, limit=limit * 2)
            out: list["SearchResult"] = []
            for item, score in keyword:
                item.score = score
                if item.score >= float(min_score):
                    out.append(item)
            return out[:limit]

    async def read_file(
        self,
        *,
        rel_path: str,
        from_line: int | None = None,
        lines: int | None = None,
    ) -> dict[str, str]:
        raw = (rel_path or "").strip()
        if not raw:
            raise ValueError("path required")
        normalized = raw.replace("\\", "/")
        if normalized.startswith("sessions/") and normalized.endswith(".md"):
            return self._read_session_virtual(
                rel_path=normalized,
                from_line=from_line,
                lines=lines,
            )

        abs_path = Path(raw)
        if not abs_path.is_absolute():
            abs_path = (self.workspace / raw).resolve()
        if not self._is_allowed_memory_file(abs_path):
            raise ValueError("path required")
        if not abs_path.exists() or not abs_path.is_file():
            return {"path": self._to_rel(abs_path), "text": ""}

        content = abs_path.read_text(encoding="utf-8", errors="replace")
        if from_line is None and lines is None:
            return {"path": self._to_rel(abs_path), "text": content}
        start = max(1, int(from_line or 1))
        count = max(1, int(lines or len(content.splitlines())))
        split = content.split("\n")
        sliced = split[start - 1 : start - 1 + count]
        return {"path": self._to_rel(abs_path), "text": "\n".join(sliced)}

    def _read_session_virtual(
        self,
        *,
        rel_path: str,
        from_line: int | None = None,
        lines: int | None = None,
    ) -> dict[str, str]:
        if not self.include_sessions:
            return {"path": rel_path, "text": ""}
        entry = self._list_session_documents().get(rel_path)
        if not entry:
            return {"path": rel_path, "text": ""}
        content = str(entry.get("content") or "")
        if from_line is None and lines is None:
            return {"path": rel_path, "text": content}
        start = max(1, int(from_line or 1))
        split = content.split("\n")
        count = max(1, int(lines or len(split)))
        sliced = split[start - 1 : start - 1 + count]
        return {"path": rel_path, "text": "\n".join(sliced)}

    def status(self) -> dict[str, Any]:
        counts = self.store.counts()
        return {
            "backend": "builtin",
            "provider": getattr(self.embedder, "model", "unknown"),
            "model": getattr(self.embedder, "model", "unknown"),
            "workspace_dir": str(self.workspace),
            "db_path": str(self.store.db_path),
            "files": counts.get("files", 0),
            "chunks": counts.get("chunks", 0),
            "source_counts": counts.get("source_counts", {}),
            "dirty_files": len(self._dirty_files),
            "search_mode": self._last_search_mode,
            "last_error": self._last_error,
            "fts_available": self.store.fts_available,
            "sessions_enabled": self.include_sessions,
            "sync": {
                "runs": self._sync_runs,
                "last_reason": self._last_sync_reason,
                "last_duration_ms": self._last_sync_duration_ms,
                "last_updated_files": self._last_sync_updated_files,
                "failures": self._sync_failures,
            },
        }

    async def _periodic_scan_loop(self) -> None:
        while self._running:
            try:
                self._scan_and_mark_dirty()
                if self._dirty_files:
                    await self.sync(reason="watch", force=False)
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
                logger.debug(f"[memory] periodic scan failed: {exc}")
            await asyncio.sleep(self.periodic_scan_seconds)

    def _scan_and_mark_dirty(self) -> None:
        current = set(self._list_documents().keys())
        added_or_removed = current.symmetric_difference(self._tracked_files)
        if added_or_removed:
            self._dirty_files.update(added_or_removed)
        self._tracked_files = current

    def _list_documents(self) -> dict[str, dict[str, Any]]:
        docs: dict[str, dict[str, Any]] = {}
        for p in self._list_memory_files():
            docs[str(p)] = {
                "kind": "file",
                "path": p,
                "source": self._resolve_source(p),
                "label": p.name,
            }
        if self.include_sessions:
            for key, entry in self._list_session_documents().items():
                docs[key] = entry
        return docs

    def _list_memory_files(self) -> list[Path]:
        files: list[Path] = []
        root = self.workspace
        for name in ("MEMORY.md", "memory.md"):
            p = root / name
            if p.exists() and p.is_file():
                files.append(p.resolve())
        if self._memory_dir.exists():
            for p in sorted(self._memory_dir.glob("*.md")):
                if p.is_file():
                    files.append(p.resolve())
        return files

    def _list_session_documents(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        sessions_dir = self._sessions_dir
        if sessions_dir is None or not sessions_dir.exists():
            return out
        for file_path in sorted(sessions_dir.glob("*.jsonl")):
            if not file_path.is_file():
                continue
            content = self._extract_session_text(file_path)
            if not content:
                continue
            virtual_path = f"sessions/{file_path.stem}.md"
            try:
                mtime = float(file_path.stat().st_mtime)
            except Exception:
                mtime = 0.0
            out[virtual_path] = {
                "kind": "content",
                "source": "sessions",
                "content": content,
                "mtime": mtime,
                "label": file_path.name,
            }
        return out

    def _extract_session_text(self, file_path: Path) -> str:
        lines: list[str] = []
        try:
            with file_path.open("r", encoding="utf-8", errors="replace") as f:
                for raw in f:
                    text = raw.strip()
                    if not text:
                        continue
                    try:
                        item = json.loads(text)
                    except Exception:
                        continue
                    if item.get("_type") == "metadata":
                        continue
                    role = str(item.get("role") or "").strip().lower()
                    content = str(item.get("content") or "").strip()
                    if role not in {"user", "assistant"} or not content:
                        continue
                    if content in {"__SILENT__", "HEARTBEAT_OK"}:
                        continue
                    label = "User" if role == "user" else "Assistant"
                    lines.append(f"{label}: {content}")
                    if len(lines) >= self.sessions_max_messages:
                        lines = lines[-self.sessions_max_messages :]
            if not lines:
                return ""
            title = f"# Session {file_path.stem}\n\n"
            return title + "\n".join(lines) + "\n"
        except Exception:
            return ""

    def _resolve_source(self, file_path: Path) -> str:
        return "memory" if file_path.name.upper() in _EVERGREEN_FILES else "daily"

    def _is_allowed_memory_file(self, abs_path: Path) -> bool:
        try:
            resolved = abs_path.resolve()
        except Exception:
            return False
        workspace = self.workspace.resolve()
        memory_dir = (workspace / "memory").resolve()
        if resolved.name in {"MEMORY.md", "memory.md"} and resolved.parent == workspace:
            return True
        if resolved.suffix.lower() != ".md":
            return False
        return resolved.parent == memory_dir

    def _to_rel(self, abs_path: Path) -> str:
        try:
            return str(abs_path.resolve().relative_to(self.workspace.resolve())).replace("\\", "/")
        except Exception:
            return str(abs_path)
