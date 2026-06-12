"""会话管理：将对话历史持久化为 JSONL 文件。"""

import json
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

from auraeve.providers.base import backfill_tool_context_start
from auraeve.utils.helpers import ensure_dir, safe_filename


@dataclass
class Session:
    """以 JSONL 格式存储的对话会话。"""

    key: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_consolidated: int = 0

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.messages.append(msg)
        self.updated_at = datetime.now()

    def get_history(self, max_messages: int = 500) -> list[dict[str, Any]]:
        """获取最近的消息，供 LLM 使用。保留 tool 调用相关字段以维持消息完整性。"""
        _KEEP_KEYS = {"role", "content", "tool_calls", "tool_call_id", "name"}
        start_index = max(len(self.messages) - max_messages, 0)
        start_index = backfill_tool_context_start(self.messages, start_index)
        return [
            {k: v for k, v in m.items() if k in _KEEP_KEYS}
            for m in self.messages[start_index:]
        ]

    def replace_history(self, messages: list[dict]) -> None:
        """压缩发生时替换历史消息，保留压缩结果携带的扩展字段。"""
        self.messages = [{**m, "content": m.get("content", "")} for m in messages]
        self.last_consolidated = 0
        self.updated_at = datetime.now()

    def clear(self) -> None:
        self.messages = []
        self.last_consolidated = 0
        self.updated_at = datetime.now()


class SessionManager:
    """将对话会话管理为 JSONL 文件。"""

    def __init__(self, sessions_dir: Path):
        self.sessions_dir = ensure_dir(sessions_dir)
        self._cache: dict[str, Session] = {}

    def _get_session_path(self, key: str) -> Path:
        safe_key = safe_filename(key.replace(":", "_"))
        return self.sessions_dir / f"{safe_key}.jsonl"

    def get_or_create(self, key: str) -> Session:
        if key in self._cache:
            return self._cache[key]
        session = self._load(key)
        if session is None:
            session = Session(key=key)
        self._cache[key] = session
        return session

    def _load(self, key: str) -> Session | None:
        path = self._get_session_path(key)
        return self._load_from_path(path, fallback_key=key)

    def _load_from_path(self, path: Path, *, fallback_key: str | None = None) -> Session | None:
        if not path.exists():
            return None
        try:
            messages = []
            metadata = {}
            created_at = None
            updated_at = None
            last_consolidated = 0
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    if data.get("_type") == "metadata":
                        metadata = data.get("metadata", {})
                        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
                        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None
                        last_consolidated = data.get("last_consolidated", 0)
                    else:
                        messages.append(data)
            key = str(metadata.get("key") or fallback_key or self._key_from_legacy_path(path))
            return Session(
                key=key,
                messages=messages,
                created_at=created_at or datetime.now(),
                updated_at=updated_at or created_at or datetime.now(),
                metadata=metadata,
                last_consolidated=last_consolidated
            )
        except Exception as e:
            logger.warning(f"加载会话 {path} 失败：{e}")
            return None

    def save(self, session: Session) -> None:
        path = self._get_session_path(session.key)
        session.metadata.setdefault("key", session.key)
        with open(path, "w") as f:
            metadata_line = {
                "_type": "metadata",
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "metadata": session.metadata,
                "last_consolidated": session.last_consolidated
            }
            f.write(json.dumps(metadata_line) + "\n")
            for msg in session.messages:
                f.write(json.dumps(msg) + "\n")
        self._cache[session.key] = session

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def create(self, prefix: str = "webui") -> Session:
        key = f"{prefix}:{uuid.uuid4().hex[:12]}"
        session = Session(key=key, metadata={"key": key, "title": "新对话"})
        self.save(session)
        return session

    def delete(self, key: str) -> bool:
        self.invalidate(key)
        path = self._get_session_path(key)
        if not path.exists():
            return False
        path.unlink()
        return True

    def list_sessions(self, prefix: str | None = None) -> list[Session]:
        sessions: list[Session] = []
        seen: set[str] = set()
        for cached in self._cache.values():
            if prefix is None or cached.key.startswith(f"{prefix}:"):
                sessions.append(cached)
                seen.add(cached.key)
        for path in self.sessions_dir.glob("*.jsonl"):
            session = self._load_from_path(path)
            if session is None or session.key in seen:
                continue
            if prefix is not None and not session.key.startswith(f"{prefix}:"):
                continue
            sessions.append(session)
            seen.add(session.key)
        return sorted(sessions, key=lambda item: item.updated_at, reverse=True)

    @staticmethod
    def _key_from_legacy_path(path: Path) -> str:
        stem = path.stem
        if "_" not in stem:
            return stem
        head, tail = stem.split("_", 1)
        return f"{head}:{tail}"
