"""子智能体进度上报。

简化版，去掉了审批请求、告警等复杂接口。
"""
from __future__ import annotations

import abc


class TaskReporter(abc.ABC):
    """上报接口。"""

    @abc.abstractmethod
    async def report_progress(
        self,
        task_id: str,
        step: int,
        message: str,
        tool_calls: int = 0,
        tokens_used: int = 0,
    ) -> None: ...

    @abc.abstractmethod
    async def report_done(
        self,
        task_id: str,
        success: bool,
        result: str,
    ) -> None: ...
