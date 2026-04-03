from __future__ import annotations

import json
from typing import Any

from auraeve.agent.tasks import TaskStore
from auraeve.agent.tools.base import Tool


class TaskCreateTool(Tool):
    def __init__(self, store: TaskStore):
        self._store = store

    @property
    def name(self) -> str:
        return "TaskCreate"

    @property
    def description(self) -> str:
        return (
            "创建一个新任务。适合在复杂工作开始时拆出清晰的任务项。"
            "任务应写成明确可执行的步骤，默认状态为 pending。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "minLength": 1},
                "description": {"type": "string", "minLength": 1},
                "activeForm": {"type": "string"},
                "owner": {"type": "string"},
                "blocks": {"type": "array", "items": {"type": "string"}},
                "blockedBy": {"type": "array", "items": {"type": "string"}},
                "metadata": {"type": "object"},
            },
            "required": ["subject", "description"],
        }

    async def execute(self, **kwargs: Any) -> str:
        task = self._store.create_task(
            subject=kwargs["subject"],
            description=kwargs["description"],
            active_form=kwargs.get("activeForm"),
            owner=kwargs.get("owner"),
            blocks=kwargs.get("blocks"),
            blocked_by=kwargs.get("blockedBy"),
            metadata=kwargs.get("metadata"),
        )
        return json.dumps(task.to_payload(), ensure_ascii=False)
