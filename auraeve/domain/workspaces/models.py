"""Workspace domain models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class WorkspaceRecord:
    workspace_id: str
    path: str
    repo_root: str
    default_branch: str = ""
    active_branch: str = ""
    status: str = "ready"
    metadata: dict[str, object] = field(default_factory=dict)

