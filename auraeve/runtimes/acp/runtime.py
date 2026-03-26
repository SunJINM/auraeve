"""ACP runtime scaffold."""

from __future__ import annotations

from auraeve.runtimes.acp.contracts import ACPRunRequest, ACPRunResult


class ACPRuntime:
    name = "acp"

    async def start_run(self, request: ACPRunRequest) -> ACPRunResult:
        return ACPRunResult(
            session_id=request.session_id,
            status="accepted",
            metadata=dict(request.metadata),
        )
