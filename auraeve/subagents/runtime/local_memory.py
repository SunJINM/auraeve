"""子体本地记忆存储。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class LocalMemoryStore:
    """子体双层记忆：working_memory（任务态）+ local_long_memory（跨任务持久）。"""

    def __init__(self, node_id: str, storage_dir: Path | None = None) -> None:
        self.node_id = node_id
        self._working: dict[str, Any] = {}
        self._storage_dir = storage_dir
        self._long_memory: list[dict] = []
        if storage_dir:
            self._long_file = storage_dir / f"{node_id}_memory.json"
            self._load_long_memory()

    def _load_long_memory(self) -> None:
        if self._long_file.exists():
            try:
                self._long_memory = json.loads(self._long_file.read_text("utf-8"))
            except Exception:
                self._long_memory = []

    def _save_long_memory(self) -> None:
        if self._storage_dir:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            self._long_file.write_text(
                json.dumps(self._long_memory, ensure_ascii=False, indent=2), "utf-8"
            )

    # ── Working Memory（任务态）──

    def set_working(self, key: str, value: Any) -> None:
        self._working[key] = value

    def get_working(self, key: str, default: Any = None) -> Any:
        return self._working.get(key, default)

    def clear_working(self) -> None:
        self._working.clear()

    def get_working_context(self) -> str:
        if not self._working:
            return ""
        lines = [f"- {k}: {v}" for k, v in self._working.items()]
        return "\n".join(lines)

    # ── Long Memory（跨任务持久）──

    def add_long_memory(self, content: str, domain: str = "general",
                        confidence: float = 1.0) -> None:
        entry = {
            "content": content,
            "domain": domain,
            "confidence": confidence,
            "created_at": time.time(),
        }
        self._long_memory.append(entry)
        self._save_long_memory()

    def search_long_memory(self, keyword: str) -> list[dict]:
        return [m for m in self._long_memory if keyword.lower() in m["content"].lower()]

    def get_long_memory_context(self, limit: int = 20) -> str:
        recent = self._long_memory[-limit:]
        if not recent:
            return ""
        lines = [f"- [{m.get('domain', '')}] {m['content']}" for m in recent]
        return "\n".join(lines)
