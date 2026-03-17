"""Scheduler：自适应任务调度。"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from auraeve.subagents.data.models import NodeSession, Task
from auraeve.subagents.data.repositories import SubagentDB
from .capability_tracker import CapabilityTracker


@dataclass
class SchedulerWeights:
    capability: float = 0.4
    load: float = 0.35
    priority: float = 0.25


class Scheduler:
    """综合能力评分 + 负载 + 优先级的自适应调度器。"""

    def __init__(
        self,
        db: SubagentDB,
        tracker: CapabilityTracker,
        weights: SchedulerWeights | None = None,
        max_node_tasks: int = 3,
    ) -> None:
        self._db = db
        self._tracker = tracker
        self._weights = weights or SchedulerWeights()
        self._max_node_tasks = max_node_tasks

    def select_node(self, task: Task) -> str | None:
        """为任务选择最优子体，返回 node_id。无可用子体返回 None。"""
        online_nodes = self._db.get_online_nodes()
        if not online_nodes:
            return None

        domain = self._infer_domain(task.goal)
        best_node: str | None = None
        best_score = -1.0

        for node in online_nodes:
            load = self._db.get_running_count(node.node_id)
            if load >= self._max_node_tasks:
                continue

            cap_score = self._tracker.get_score(node.node_id, domain)
            load_ratio = load / self._max_node_tasks
            priority_match = task.priority / 9.0

            score = (
                self._weights.capability * cap_score
                + self._weights.load * (1 - load_ratio)
                + self._weights.priority * priority_match
            )

            if score > best_score:
                best_score = score
                best_node = node.node_id

        if best_node:
            logger.debug(f"[scheduler] 任务 {task.task_id} 分配给 {best_node}（score={best_score:.2f}）")

        return best_node

    def _infer_domain(self, goal: str) -> str:
        goal_lower = goal.lower()
        if any(k in goal_lower for k in ("shell", "命令", "执行", "运行", "安装")):
            return "shell"
        if any(k in goal_lower for k in ("文件", "读取", "写入", "编辑")):
            return "file_ops"
        if any(k in goal_lower for k in ("搜索", "网页", "爬取", "api")):
            return "web"
        return "general"
