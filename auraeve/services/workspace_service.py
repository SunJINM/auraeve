"""Workspace service helpers."""

from __future__ import annotations

from pathlib import Path

from auraeve.domain.workspaces.models import WorkspaceRecord


class WorkspaceService:
    def build_workspace(
        self,
        workspace_id: str,
        path: Path | str,
        repo_root: Path | str | None = None,
        default_branch: str = "",
        active_branch: str = "",
        status: str = "ready",
        metadata: dict[str, object] | None = None,
    ) -> WorkspaceRecord:
        resolved_path = Path(path).expanduser().resolve(strict=False)
        resolved_repo_root = (
            Path(repo_root).expanduser().resolve(strict=False)
            if repo_root is not None
            else resolved_path
        )
        return WorkspaceRecord(
            workspace_id=workspace_id,
            path=str(resolved_path),
            repo_root=str(resolved_repo_root),
            default_branch=default_branch,
            active_branch=active_branch,
            status=status,
            metadata=dict(metadata or {}),
        )
