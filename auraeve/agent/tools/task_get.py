from __future__ import annotations

from typing import Any

from auraeve.agent.tasks import TaskStore
from auraeve.agent.tools.base import Tool, ToolExecutionResult
from auraeve.agent_runtime.tool_runtime_context import (
    TaskReadSnapshot,
    get_current_tool_runtime_context,
)


TASK_UNCHANGED_STUB = (
    "Task unchanged since the latest TaskGet/TaskUpdate in this turn. "
    "Prefer TaskList to find the next available task unless you specifically need this task again."
)


class TaskGetTool(Tool):
    def __init__(self, store: TaskStore):
        self._store = store

    @property
    def name(self) -> str:
        return "TaskGet"

    @property
    def description(self) -> str:
        return (
            "按 taskId 读取单个任务的完整详情。"
            "适合在开始工作前获取任务描述、状态和依赖关系。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "taskId": {"type": "string", "minLength": 1},
            },
            "required": ["taskId"],
        }

    async def execute(self, **kwargs: Any) -> ToolExecutionResult:
        task_id = kwargs["taskId"]
        task = self._store.get_task(task_id)
        if task is None:
            return ToolExecutionResult(
                content="Task not found",
                data={"task": None},
            )

        payload = {
            "id": task.id,
            "subject": task.subject,
            "description": task.description,
            "status": task.status.value,
            "blocks": list(task.blocks),
            "blockedBy": list(task.blocked_by),
        }
        ctx = get_current_tool_runtime_context()
        if ctx is not None:
            snapshot = ctx.task_reads.get(task_id)
            if (
                snapshot is not None
                and snapshot.last_action in {"get", "update"}
                and ctx.task_reads.payload_equals(snapshot.payload, payload)
            ):
                return ToolExecutionResult(
                    content=TASK_UNCHANGED_STUB,
                    data={"type": "task_unchanged", "taskId": task_id},
                )
            ctx.task_reads.record(
                TaskReadSnapshot(task_id=task_id, payload=payload, last_action="get")
            )

        lines = [
            f"Task #{payload['id']}: {payload['subject']}",
            f"Status: {payload['status']}",
            f"Description: {payload['description']}",
        ]
        if payload["blockedBy"]:
            lines.append(
                f"Blocked by: {', '.join(f'#{item}' for item in payload['blockedBy'])}"
            )
        if payload["blocks"]:
            lines.append(f"Blocks: {', '.join(f'#{item}' for item in payload['blocks'])}")

        return ToolExecutionResult(
            content="\n".join(lines),
            data={"task": payload},
        )
