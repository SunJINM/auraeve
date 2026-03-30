from __future__ import annotations

import time
import uuid

from auraeve.external_agents.models import (
    ExternalRunRequest,
    ExternalRunResult,
    ExternalSessionHandle,
)
from auraeve.external_agents.registry import ExternalAgentRegistry
from auraeve.external_agents.runtime import ExternalAgentRuntime
from auraeve.external_agents.store import ExternalAgentSessionStore


class ExternalAgentService:
    def __init__(
        self,
        *,
        runtime: ExternalAgentRuntime,
        registry: ExternalAgentRegistry,
        store: ExternalAgentSessionStore,
    ) -> None:
        self._runtime = runtime
        self._registry = registry
        self._store = store

    def pick_target(self, *, task: str, requested_target: str) -> str:
        if requested_target != "auto":
            return requested_target
        lower = task.lower()
        if any(
            keyword in lower
            for keyword in ("review", "审查", "架构", "方案", "分析", "评估")
        ):
            return "claude"
        return "codex"

    def resolve_reusable_session(
        self,
        *,
        origin_session_key: str,
        target: str,
        cwd: str,
        mode: str,
    ) -> ExternalSessionHandle | None:
        if mode != "session":
            return None
        return self._store.find_reusable(
            origin_session_key=origin_session_key,
            target=target,
            cwd=cwd,
        )

    async def run(
        self,
        *,
        task: str,
        requested_target: str,
        cwd: str,
        mode: str,
        label: str | None,
        timeout_s: int,
        context_mode: str,
        expected_output: str,
        origin_session_key: str,
        execution_target: str = "local",
    ) -> ExternalRunResult:
        target = self.pick_target(task=task, requested_target=requested_target)
        reusable = self.resolve_reusable_session(
            origin_session_key=origin_session_key,
            target=target,
            cwd=cwd,
            mode=mode,
        )
        session_id = reusable.session_id if reusable else f"ext-{uuid.uuid4().hex[:12]}"
        handle = reusable or await self._runtime.ensure_session(
            target=target,
            session_id=session_id,
            cwd=cwd,
            mode=mode,
            origin_session_key=origin_session_key,
            execution_target=execution_target,
        )
        self._store.save(handle)
        request = ExternalRunRequest(
            task=task,
            target=target,
            cwd=cwd,
            mode=mode,
            label=label,
            timeout_s=timeout_s,
            context_mode=context_mode,
            expected_output=expected_output,
            session_id=handle.session_id,
            execution_target=execution_target,
        )
        result = await self._runtime.run_turn(request, handle)
        latest = self._store.get(handle.session_id) or handle
        latest.updated_at = time.time()
        latest.status = "idle" if result.status == "ok" else "failed"
        latest.last_run_summary = result.summary
        latest.last_error = result.error
        self._store.save(latest)
        return result

    async def status(self, session_id: str) -> ExternalSessionHandle | None:
        handle = self._store.get(session_id)
        if handle is None:
            return None
        latest = await self._runtime.get_status(handle)
        self._store.save(latest)
        return latest

    async def cancel(self, session_id: str) -> ExternalSessionHandle | None:
        handle = self._store.get(session_id)
        if handle is None:
            return None
        latest = await self._runtime.cancel(handle)
        latest.last_error = None
        self._store.save(latest)
        return latest

    async def close(self, session_id: str) -> ExternalSessionHandle | None:
        handle = self._store.get(session_id)
        if handle is None:
            return None
        latest = await self._runtime.close(handle)
        self._store.save(latest)
        return latest
