"""Artifact service helpers."""

from __future__ import annotations

import uuid

from auraeve.domain.artifacts.models import ArtifactRecord


class ArtifactService:
    def build_artifact(
        self,
        session_id: str,
        run_id: str,
        kind: str,
        path: str,
        label: str = "",
        metadata: dict[str, object] | None = None,
    ) -> ArtifactRecord:
        return ArtifactRecord(
            artifact_id=str(uuid.uuid4()),
            session_id=session_id,
            run_id=run_id,
            kind=kind,
            path=path,
            label=label,
            metadata=dict(metadata or {}),
        )

