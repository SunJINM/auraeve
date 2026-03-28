"""PatchSet domain model."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PatchSet:
    patch_id: str
    session_id: str
    run_id: str
    files: list[str]
    status: str  # proposed | applied | rejected
    created_at: str = ""
    applied_at: str | None = None
