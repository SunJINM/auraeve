"""CapabilityTracker：子体能力评估与经验学习。"""

from __future__ import annotations

from auraeve.subagents.data.models import CapabilityScore
from auraeve.subagents.data.repositories import SubagentDB


class CapabilityTracker:
    """记录子体执行历史，供 Scheduler 使用。"""

    def __init__(self, db: SubagentDB) -> None:
        self._db = db

    def record_outcome(
        self, node_id: str, domain: str, success: bool, duration_s: float
    ) -> None:
        self._db.record_task_outcome(node_id, domain, success, duration_s)

    def get_score(self, node_id: str, domain: str) -> float:
        scores = self._db.get_capability_scores(node_id)
        for s in scores:
            if s.capability_domain == domain:
                return s.score
        return 0.5  # 未知能力

    def get_all_scores(self, node_id: str) -> list[CapabilityScore]:
        return self._db.get_capability_scores(node_id)
