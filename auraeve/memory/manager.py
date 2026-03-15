from __future__ import annotations

import asyncio
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

        self._memory_dir = self.workspace / "memory"
        self._sync_lock = asyncio.Lock()
        self._dirty_files: set[str] = set()
        self._tracked_files: set[str] = set()
        self._running = False
        self._scan_task: asyncio.Task | None = None
        self._last_search_mode = "hybrid"
        self._last_error: str | None = None

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
        for p in self._list_memory_files():
            self._dirty_files.add(str(p))

    async def sync(self, *, reason: str = "manual", force: bool = False) -> int:
        async with self._sync_lock:
            current_files = {str(p): p for p in self._list_memory_files()}
            if force:
                target_paths = set(current_files.keys())
                deleted_paths = self._tracked_files - set(current_files.keys())
            else:
                target_paths = set(self._dirty_files)
                deleted_paths = {p for p in target_paths if p not in current_files}
                target_paths = {p for p in target_paths if p in current_files}
                deleted_paths |= self._tracked_files - set(current_files.keys())

            indexed_files = 0
            for path_str in sorted(target_paths):
                file_path = current_files[path_str]
                source = self._resolve_source(file_path)
                try:
                    chunks = await self.store.index_file(file_path, source, self.embedder)
                    if chunks > 0:
                        indexed_files += 1
                        logger.debug(f"  索引 {file_path.name}：{chunks} 个片段")
                except Exception as exc:  # noqa: BLE001
                    self._last_error = str(exc)
                    logger.warning(f"  索引 {file_path.name} 失败：{exc}")

            for deleted in sorted(deleted_paths):
                try:
                    self.store.delete_file(deleted)
                except Exception as exc:  # noqa: BLE001
                    self._last_error = str(exc)
                    logger.warning(f"  清理已删除记忆文件索引失败 {deleted}: {exc}")

            self._tracked_files = set(current_files.keys())
            self._dirty_files.difference_update(target_paths | deleted_paths)
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
            "dirty_files": len(self._dirty_files),
            "search_mode": self._last_search_mode,
            "last_error": self._last_error,
            "fts_available": self.store.fts_available,
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
        current = {str(p) for p in self._list_memory_files()}
        added_or_removed = current.symmetric_difference(self._tracked_files)
        if added_or_removed:
            self._dirty_files.update(added_or_removed)
        self._tracked_files = current

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
