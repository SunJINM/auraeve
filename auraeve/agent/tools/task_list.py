from __future__ import annotations

import json
from typing import Any

from auraeve.agent.tasks import TaskStore
from auraeve.agent.tools.base import Tool


class TaskListTool(Tool):
    def __init__(self, store: TaskStore):
        self._store = store

    @property
    def name(self) -> str:
        return "TaskList"

    @property
    def description(self) -> str:
        return "列出当前任务列表。完成一个任务后，用它查看下一个可执行任务。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self, **kwargs: Any) -> str:
        tasks = [task.to_payload() for task in self._store.list_tasks()]
        return json.dumps({"tasks": tasks}, ensure_ascii=False)
