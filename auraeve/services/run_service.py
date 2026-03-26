"""Run service helpers."""

from __future__ import annotations

import uuid
from pathlib import Path

from auraeve.domain.runs.event_store import RunEventStore
from auraeve.domain.runs.models import RunEvent


class RunService:
    def __init__(self, event_store: RunEventStore | Path | str) -> None:
        if isinstance(event_store, (Path, str)):
            event_store = RunEventStore(Path(event_store))
        self._store = event_store

    def record_prompt(
        self,
        session_id: str,
        prompt: str,
        metadata: dict[str, object] | None = None,
    ) -> str:
        """Record a prompt as a user_prompt event and return the generated run id."""
        run_id = str(uuid.uuid4())
        self._store.append(
            RunEvent(
                event_id=str(uuid.uuid4()),
                session_id=session_id,
                run_id=run_id,
                event_type="user_prompt",
                payload={"prompt": prompt, "metadata": dict(metadata or {})},
            )
        )
        return run_id

    def list_events(self, session_id: str) -> list[RunEvent]:
        return self._store.list_for_session(session_id)
