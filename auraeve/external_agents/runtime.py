from __future__ import annotations

from abc import ABC, abstractmethod

from auraeve.external_agents.models import (
    ExternalRunRequest,
    ExternalRunResult,
    ExternalSessionHandle,
)


class ExternalAgentRuntime(ABC):
    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    async def run_turn(
        self, request: ExternalRunRequest, handle: ExternalSessionHandle
    ) -> ExternalRunResult:
        raise NotImplementedError

    @abstractmethod
    async def cancel(self, handle: ExternalSessionHandle) -> ExternalSessionHandle:
        raise NotImplementedError

    @abstractmethod
    async def close(self, handle: ExternalSessionHandle) -> ExternalSessionHandle:
        raise NotImplementedError

    @abstractmethod
    async def get_status(self, handle: ExternalSessionHandle) -> ExternalSessionHandle:
        raise NotImplementedError
