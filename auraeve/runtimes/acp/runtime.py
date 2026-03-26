"""ACP runtime scaffold."""

from __future__ import annotations

from auraeve.services.run_service import RunService
from auraeve.runtimes.acp.contracts import ACPRunRequest, ACPRunResult


class ACPRuntime:
    name = "acp"

    def __init__(self, run_service: RunService) -> None:
        self._runs = run_service

    async def start_run(self, request: ACPRunRequest) -> ACPRunResult:
        run_id = self._runs.record_prompt(
            session_id=request.session_id,
            prompt=request.prompt,
            metadata=dict(request.metadata),
        )
        return ACPRunResult(
            session_id=request.session_id,
            status="accepted",
            metadata={
                "request": dict(request.metadata),
                "runtime": {"run_id": run_id},
            },
        )
