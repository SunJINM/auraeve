"""Artifact domain models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ArtifactRecord:
    artifact_id: str
    session_id: str
    run_id: str
    kind: str
    path: str
    label: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

