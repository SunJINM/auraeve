"""fan-out 子体结果暂存，等所有分支完成后一次性合并注入母体。"""
from __future__ import annotations


class PendingResultStore:
    """线程安全（asyncio 单线程）的内存暂存。key = trace_id。"""

    def __init__(self) -> None:
        # trace_id -> {task_id -> result_dict}
        self._store: dict[str, dict[str, dict]] = {}

    def add(self, trace_id: str, task_id: str, result: dict) -> None:
        if trace_id not in self._store:
            self._store[trace_id] = {}
        self._store[trace_id][task_id] = result  # 幂等：重复 task_id 覆盖

    def is_complete(self, trace_id: str, total: int) -> bool:
        return len(self._store.get(trace_id, {})) >= total

    def collect_and_clear(self, trace_id: str) -> list[dict]:
        results = list(self._store.pop(trace_id, {}).values())
        return results
