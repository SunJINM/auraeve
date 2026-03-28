"""Application bootstrap helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import auraeve.config as cfg
from auraeve.app.container import AppContainer
from auraeve.domain.runs.event_store import RunEventStore
from auraeve.domain.sessions.repository import SessionRepository
from auraeve.runtimes.acp.runtime import ACPRuntime
from auraeve.services.artifact_service import ArtifactService
from auraeve.services.run_service import RunService
from auraeve.services.session_service import SessionService
from auraeve.services.workspace_service import WorkspaceService
from auraeve.webui.dev_session_service import DevSessionService


def create_application(state_dir: Path | None = None) -> AppContainer:
    """Build the composed application container used by CLI and runtime entrypoints."""
    resolved_state_dir = (state_dir or cfg.resolve_state_dir()).expanduser().resolve(strict=False)
    dev_runtime_dir = resolved_state_dir / "dev_runtime"
    dev_runtime_dir.mkdir(parents=True, exist_ok=True)

    session_service = SessionService(SessionRepository())
    workspace_service = WorkspaceService()
    run_service = RunService(RunEventStore(dev_runtime_dir / "events"))
    artifact_service = ArtifactService()
    dev_session_service = DevSessionService(session_service)

    application = AppContainer(
        session_service=session_service,
        workspace_service=workspace_service,
        run_service=run_service,
        artifact_service=artifact_service,
        dev_session_service=dev_session_service,
    )
    application.runtime_registry.register("acp", ACPRuntime(run_service))
    return application


async def _run_runtime(application: AppContainer, terminal_mode: bool) -> None:
    from main import main as runtime_main

    await runtime_main(terminal_mode=terminal_mode, application=application)


def run_application(terminal_mode: bool = False) -> AppContainer:
    """Create the application container and enter the runtime entrypoint."""
    application = create_application()
    asyncio.run(_run_runtime(application, terminal_mode))
    return application
