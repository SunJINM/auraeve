from __future__ import annotations

import json
from typing import Any

from auraeve.agent.tasks import TaskStore
from auraeve.agent.tools.base import Tool


class TaskGetTool(Tool):
    def __init__(self, store: TaskStore):
        self._store = store

    @property
    def name(self) -> str:
        return "TaskGet"

    @property
    def description(self) -> str:
        return "读取单个任务的最新状态。更新任务前，先用它确认当前状态。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "taskId": {"type": "string", "minLength": 1},
            },
            "required": ["taskId"],
        }

    async def execute(self, **kwargs: Any) -> str:
        task = self._store.get_task(kwargs["taskId"])
        if task is None:
            return json.dumps({"error": "task_not_found", "taskId": kwargs["taskId"]}, ensure_ascii=False)
        return json.dumps(task.to_payload(), ensure_ascii=False)
