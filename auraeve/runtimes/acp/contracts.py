"""Minimal contracts for the ACP runtime."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ACPRunRequest:
    session_id: str
    prompt: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ACPRunResult:
    session_id: str
    status: str
    metadata: dict[str, object] = field(default_factory=dict)
