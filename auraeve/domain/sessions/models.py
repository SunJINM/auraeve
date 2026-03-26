"""Unified session domain models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SessionRecord:
    session_id: str
    session_key: str
    session_type: str
    runtime_type: str
    agent_id: str
    workspace_id: str
    thread_id: str
    state: str
    metadata: dict[str, object] = field(default_factory=dict)
