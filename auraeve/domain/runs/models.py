"""Run event domain models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RunEvent:
    event_id: str
    session_id: str
    run_id: str
    event_type: str
    payload: dict[str, object]
