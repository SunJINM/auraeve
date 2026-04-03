from __future__ import annotations

import json
from typing import Any

from auraeve.agent.tasks import TaskStatus, TaskStore
from auraeve.agent.tools.base import Tool


class TaskUpdateTool(Tool):
    def __init__(self, store: TaskStore):
        self._store = store

    @property
    def name(self) -> str:
        return "TaskUpdate"

    @property
    def description(self) -> str:
        return (
            "增量更新任务。开始执行前把任务标记为 in_progress，完成后立刻标记为 completed。"
            "修改前应先读取最新状态。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "taskId": {"type": "string", "minLength": 1},
                "subject": {"type": "string"},
                "description": {"type": "string"},
                "activeForm": {"type": "string"},
                "owner": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": [TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value, TaskStatus.COMPLETED.value],
                },
                "blocks": {"type": "array", "items": {"type": "string"}},
                "blockedBy": {"type": "array", "items": {"type": "string"}},
                "metadata": {"type": "object"},
                "deleted": {"type": "boolean"},
            },
            "required": ["taskId"],
        }

    async def execute(self, **kwargs: Any) -> str:
        task_id = kwargs["taskId"]
        if kwargs.get("deleted"):
            self._store.delete_task(task_id)
            return json.dumps({"deleted": True, "taskId": task_id}, ensure_ascii=False)
        status = kwargs.get("status")
        updated = self._store.update_task(
            task_id,
            subject=kwargs.get("subject"),
            description=kwargs.get("description"),
            active_form=kwargs.get("activeForm"),
            owner=kwargs.get("owner"),
            status=TaskStatus(status) if status else None,
            blocks=kwargs.get("blocks"),
            blocked_by=kwargs.get("blockedBy"),
            metadata=kwargs.get("metadata"),
        )
        return json.dumps(updated.to_payload(), ensure_ascii=False)
