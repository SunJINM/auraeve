from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from auraeve.external_agents.models import ExternalSessionHandle


class ExternalAgentSessionStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load_all(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _save_all(self, payload: dict[str, dict]) -> None:
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save(self, handle: ExternalSessionHandle) -> None:
        payload = self._load_all()
        payload[handle.session_id] = asdict(handle)
        self._save_all(payload)

    def get(self, session_id: str) -> ExternalSessionHandle | None:
        payload = self._load_all().get(session_id)
        return None if payload is None else ExternalSessionHandle(**payload)

    def list(self) -> list[ExternalSessionHandle]:
        return [ExternalSessionHandle(**item) for item in self._load_all().values()]

    def find_reusable(
        self,
        *,
        origin_session_key: str,
        target: str,
        cwd: str,
    ) -> ExternalSessionHandle | None:
        for handle in self.list():
            if (
                handle.origin_session_key == origin_session_key
                and handle.target == target
                and handle.cwd == cwd
                and handle.mode == "session"
                and handle.status not in {"closed", "failed"}
            ):
                return handle
        return None
