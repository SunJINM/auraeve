from __future__ import annotations

import asyncio
import time

from auraeve.external_agents.models import (
    ExternalRunRequest,
    ExternalRunResult,
    ExternalSessionHandle,
)
from auraeve.external_agents.runtime import ExternalAgentRuntime


class _DefaultProcessRunner:
    async def run(
        self, argv: list[str], cwd: str, timeout_s: int
    ) -> dict[str, str | int]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
        except FileNotFoundError as exc:
            return {
                "stdout": "",
                "stderr": f"command not found: {argv[0]}",
                "returncode": 127,
            }
        except Exception as exc:
            return {
                "stdout": "",
                "stderr": str(exc),
                "returncode": 1,
            }

        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            return {
                "stdout": "",
                "stderr": f"command timed out after {timeout_s}s",
                "returncode": 124,
            }

        return {
            "stdout": out.decode(errors="replace"),
            "stderr": err.decode(errors="replace"),
            "returncode": int(proc.returncode or 0),
        }


class AcpxAdapter(ExternalAgentRuntime):
    def __init__(self, *, command: str = "acpx", process_runner=None) -> None:
        self._command = command
        self._runner = process_runner or _DefaultProcessRunner()

    async def ensure_session(
        self,
        *,
        target: str,
        session_id: str,
        cwd: str,
        mode: str,
        origin_session_key: str,
        execution_target: str,
    ) -> ExternalSessionHandle:
        now = time.time()
        return ExternalSessionHandle(
            session_id=session_id,
            target=target,
            mode=mode,
            cwd=cwd,
            status="idle",
            created_at=now,
            updated_at=now,
            origin_session_key=origin_session_key,
            execution_target=execution_target,
            backend_session_ref=session_id,
        )

    async def run_turn(
        self, request: ExternalRunRequest, handle: ExternalSessionHandle
    ) -> ExternalRunResult:
        argv = [
            self._command,
            handle.target,
            "--session",
            handle.backend_session_ref or handle.session_id,
            "--cwd",
            handle.cwd,
            request.task,
        ]
        outcome = await self._runner.run(argv, handle.cwd, request.timeout_s)
        stdout = str(outcome.get("stdout") or "").strip()
        stderr = str(outcome.get("stderr") or "").strip()
        returncode = int(outcome.get("returncode") or 0)
        if returncode == 0:
            return ExternalRunResult(
                status="ok",
                target=handle.target,
                session_id=handle.session_id,
                final_text=stdout,
                summary=stdout[:200],
                artifacts=[],
                raw_output_ref=None,
                error=None,
                usage={},
                suggested_next_action=None,
                error_type=None,
                retryable=False,
                session_survived=handle.mode == "session",
            )
        error_type = "process_error"
        retryable = True
        if returncode == 5 or "permission denied" in stderr.lower():
            error_type = "permission_denied_noninteractive"
            retryable = False
        return ExternalRunResult(
            status="error",
            target=handle.target,
            session_id=handle.session_id,
            final_text="",
            summary=stderr[:200] or "external agent failed",
            artifacts=[],
            raw_output_ref=None,
            error=stderr or "external agent failed",
            usage={},
            suggested_next_action="inspect_error",
            error_type=error_type,
            retryable=retryable,
            session_survived=False,
        )

    async def cancel(self, handle: ExternalSessionHandle) -> ExternalSessionHandle:
        handle.status = "aborted"
        handle.updated_at = time.time()
        return handle

    async def close(self, handle: ExternalSessionHandle) -> ExternalSessionHandle:
        handle.status = "closed"
        handle.updated_at = time.time()
        return handle

    async def get_status(self, handle: ExternalSessionHandle) -> ExternalSessionHandle:
        handle.updated_at = time.time()
        return handle
