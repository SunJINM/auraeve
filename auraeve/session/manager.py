"""Legacy transcript manager for chat-history compatibility storage.

The ACP redesign keeps this module only for raw transcript/history persistence
used by older chat flows. Structured session identity now lives under
``auraeve.domain.sessions`` and should be preferred for any new runtime.
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

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
        """获取最近的消息（仅保留 role 和 content 字段，供 LLM 使用）。"""
        return [{"role": m["role"], "content": m["content"]} for m in self.messages[-max_messages:]]

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
        if not path.exists():
            return None
        try:
            messages = []
            metadata = {}
            created_at = None
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
                        last_consolidated = data.get("last_consolidated", 0)
                    else:
                        messages.append(data)
            return Session(
                key=key,
                messages=messages,
                created_at=created_at or datetime.now(),
                metadata=metadata,
                last_consolidated=last_consolidated
            )
        except Exception as e:
            logger.warning(f"加载会话 {key} 失败：{e}")
            return None

    def save(self, session: Session) -> None:
        path = self._get_session_path(session.key)
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
