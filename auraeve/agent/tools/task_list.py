from __future__ import annotations

from typing import Any

from auraeve.agent.tasks import TaskStore
from auraeve.agent.tools.base import Tool, ToolExecutionResult


class TaskListTool(Tool):
    def __init__(self, store: TaskStore):
        self._store = store

    @property
    def name(self) -> str:
        return "TaskList"

    @property
    def description(self) -> str:
        return (
            "列出当前任务列表。完成一个任务后，优先用它查看有哪些任务可继续推进，"
            "再决定是否需要对某个具体任务调用 TaskGet。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self, **kwargs: Any) -> ToolExecutionResult:
        all_tasks = [
            task for task in self._store.list_tasks() if not task.metadata.get("_internal")
        ]
        resolved_ids = {task.id for task in all_tasks if task.status.value == "completed"}
        tasks = [
            {
                "id": task.id,
                "subject": task.subject,
                "status": task.status.value,
                "owner": task.owner,
                "blockedBy": [item for item in task.blocked_by if item not in resolved_ids],
            }
            for task in all_tasks
        ]
        if not tasks:
            return ToolExecutionResult(content="No tasks found", data={"tasks": []})

        lines = []
        for task in tasks:
            owner = f" ({task['owner']})" if task.get("owner") else ""
            blocked = ""
            if task["blockedBy"]:
                blocked = " [blocked by " + ", ".join(f"#{item}" for item in task["blockedBy"]) + "]"
            lines.append(
                f"#{task['id']} [{task['status']}] {task['subject']}{owner}{blocked}"
            )

        return ToolExecutionResult(
            content="\n".join(lines),
            data={"tasks": tasks},
        )
