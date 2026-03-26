"""Application container for composed services and runtime registries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from auraeve.app.runtime_registry import RuntimeRegistry


@dataclass
class AppContainer:
    """Lightweight container for shared runtime services."""

    runtime_registry: RuntimeRegistry = field(default_factory=RuntimeRegistry)
    session_service: Any | None = None
    workspace_service: Any | None = None
    run_service: Any | None = None
    artifact_service: Any | None = None
    dev_session_service: Any | None = None
