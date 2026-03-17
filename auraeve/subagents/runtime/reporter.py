"""TaskReporter 接口及本地实现。"""

from __future__ import annotations

import abc
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from auraeve.subagents.data.models import MemoryDelta


class TaskReporter(abc.ABC):
    """子体上报接口。本地子体和远程子体各有实现。"""

    @abc.abstractmethod
    async def report_progress(self, task_id: str, step: int, message: str,
                              tool_calls: int = 0, tokens_used: int = 0) -> None: ...

    @abc.abstractmethod
    async def report_alert(self, task_id: str, level: str, message: str) -> None: ...

    @abc.abstractmethod
    async def report_done(self, task_id: str, success: bool, result: str,
                          artifacts: list[dict] | None = None,
                          memory_deltas: list[dict] | None = None,
                          experience: dict | None = None) -> None: ...

    @abc.abstractmethod
    async def request_approval(self, task_id: str, approval_id: str,
                               action_desc: str, risk_level: str,
                               context: dict | None = None) -> str: ...


class InProcessReporter(TaskReporter):
    """本地子体使用的进程内上报器，直接调用 Orchestrator。"""

    def __init__(self, orchestrator: Any) -> None:
        self._orch = orchestrator

    async def report_progress(self, task_id: str, step: int, message: str,
                              tool_calls: int = 0, tokens_used: int = 0) -> None:
        await self._orch.handle_progress(task_id, step, message, tool_calls, tokens_used)

    async def report_alert(self, task_id: str, level: str, message: str) -> None:
        await self._orch.handle_alert(task_id, level, message)

    async def report_done(self, task_id: str, success: bool, result: str,
                          artifacts: list[dict] | None = None,
                          memory_deltas: list[dict] | None = None,
                          experience: dict | None = None) -> None:
        await self._orch.handle_done(task_id, success, result, artifacts, memory_deltas, experience)

    async def request_approval(self, task_id: str, approval_id: str,
                               action_desc: str, risk_level: str,
                               context: dict | None = None) -> str:
        return await self._orch.handle_approval_request(
            task_id, approval_id, action_desc, risk_level, context,
        )
