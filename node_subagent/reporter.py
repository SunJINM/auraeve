"""WebSocketReporter：远程子体通过 WebSocket 上报。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from auraeve.subagents.runtime.reporter import TaskReporter

if TYPE_CHECKING:
    from auraeve.subagents.transport.ws_client import SubAgentWSClient


class WebSocketReporter(TaskReporter):
    """远程子体的上报器，通过 WebSocket 客户端发送消息到母体。"""

    def __init__(self, client: "SubAgentWSClient") -> None:
        self._client = client
        self._approval_futures: dict[str, asyncio.Future] = {}

    async def report_progress(self, task_id: str, step: int, message: str,
                              tool_calls: int = 0, tokens_used: int = 0) -> None:
        await self._client.report_progress(task_id, step, message, tool_calls, tokens_used)

    async def report_alert(self, task_id: str, level: str, message: str) -> None:
        await self._client.report_alert(task_id, level, message)

    async def report_done(self, task_id: str, success: bool, result: str,
                          artifacts: list[dict] | None = None,
                          memory_deltas: list[dict] | None = None,
                          experience: dict | None = None) -> None:
        await self._client.report_done(task_id, success, result, artifacts, memory_deltas, experience)

    async def request_approval(self, task_id: str, approval_id: str,
                               action_desc: str, risk_level: str,
                               context: dict | None = None) -> str:
        await self._client.request_approval(task_id, approval_id, action_desc, risk_level, context)

        # 等待母体审批决策
        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        self._approval_futures[approval_id] = future
        try:
            return await asyncio.wait_for(future, timeout=1800)
        except asyncio.TimeoutError:
            return "timed_out"
        finally:
            self._approval_futures.pop(approval_id, None)

    def resolve_approval(self, approval_id: str, decision: str) -> None:
        """母体审批决策到达时调用。"""
        future = self._approval_futures.get(approval_id)
        if future and not future.done():
            future.set_result(decision)
