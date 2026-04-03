from __future__ import annotations

from typing import Any

from auraeve.agent.tasks import TaskStore
from auraeve.agent.tools.base import Tool, ToolExecutionResult


class TaskCreateTool(Tool):
    def __init__(self, store: TaskStore):
        self._store = store

    @property
    def name(self) -> str:
        return "TaskCreate"

    @property
    def description(self) -> str:
        return (
            "创建一个新任务。适合在复杂、多步骤工作中建立结构化任务列表。"
            "新任务默认为 pending；需要指派负责人或建立依赖时，用 TaskUpdate 继续补充。"
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

    async def execute(self, **kwargs: Any) -> ToolExecutionResult:
        task = self._store.create_task(
            subject=kwargs["subject"],
            description=kwargs["description"],
            active_form=kwargs.get("activeForm"),
            owner=kwargs.get("owner"),
            blocks=kwargs.get("blocks"),
            blocked_by=kwargs.get("blockedBy"),
            metadata=kwargs.get("metadata"),
        )
        return ToolExecutionResult(
            content=f"Task #{task.id} created successfully: {task.subject}",
            data={
                "task": {
                    "id": task.id,
                    "subject": task.subject,
                }
            },
        )
