from __future__ import annotations

from typing import Any

from auraeve.agent.tasks import TaskStatus, TaskStore
from auraeve.agent.tools.base import Tool, ToolExecutionResult
from auraeve.agent_runtime.tool_runtime_context import (
    TaskReadSnapshot,
    get_current_tool_runtime_context,
)


class TaskUpdateTool(Tool):
    def __init__(self, store: TaskStore):
        self._store = store

    @property
    def name(self) -> str:
        return "TaskUpdate"

    @property
    def description(self) -> str:
        return (
            "更新任务状态或字段。开始工作时把任务标记为 in_progress，完成时立刻标记为 completed。"
            "完成一个任务后，优先调用 TaskList 查看下一项可执行工作。"
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
                    "enum": [
                        TaskStatus.PENDING.value,
                        TaskStatus.IN_PROGRESS.value,
                        TaskStatus.COMPLETED.value,
                        "deleted",
                    ],
                },
                "blocks": {"type": "array", "items": {"type": "string"}},
                "blockedBy": {"type": "array", "items": {"type": "string"}},
                "addBlocks": {"type": "array", "items": {"type": "string"}},
                "addBlockedBy": {"type": "array", "items": {"type": "string"}},
                "metadata": {"type": "object"},
                "deleted": {"type": "boolean"},
            },
            "required": ["taskId"],
        }

    async def execute(self, **kwargs: Any) -> ToolExecutionResult:
        task_id = kwargs["taskId"]
        existing = self._store.get_task(task_id)
        if existing is None:
            return ToolExecutionResult(
                content="Task not found",
                data={
                    "success": False,
                    "taskId": task_id,
                    "updatedFields": [],
                    "error": "Task not found",
                },
            )

        status = kwargs.get("status")
        if kwargs.get("deleted") or status == "deleted":
            self._store.delete_task(task_id)
            return ToolExecutionResult(
                content=f"Updated task #{task_id} deleted",
                data={
                    "success": True,
                    "taskId": task_id,
                    "updatedFields": ["deleted"],
                    "statusChange": {"from": existing.status.value, "to": "deleted"},
                },
            )

        updated_fields: list[str] = []
        merged_blocks = list(existing.blocks)
        merged_blocked_by = list(existing.blocked_by)

        blocks = kwargs.get("blocks")
        if blocks is not None:
            merged_blocks = [str(item) for item in blocks]
            updated_fields.append("blocks")
        add_blocks = kwargs.get("addBlocks") or []
        for block_id in add_blocks:
            block_id = str(block_id)
            if block_id not in merged_blocks:
                merged_blocks.append(block_id)
        if add_blocks:
            updated_fields.append("blocks")

        blocked_by = kwargs.get("blockedBy")
        if blocked_by is not None:
            merged_blocked_by = [str(item) for item in blocked_by]
            updated_fields.append("blockedBy")
        add_blocked_by = kwargs.get("addBlockedBy") or []
        for blocker_id in add_blocked_by:
            blocker_id = str(blocker_id)
            if blocker_id not in merged_blocked_by:
                merged_blocked_by.append(blocker_id)
        if add_blocked_by:
            updated_fields.append("blockedBy")

        merged_metadata = dict(existing.metadata)
        metadata = kwargs.get("metadata")
        if metadata is not None:
            for key, value in dict(metadata).items():
                if value is None:
                    merged_metadata.pop(str(key), None)
                else:
                    merged_metadata[str(key)] = value
            updated_fields.append("metadata")

        if kwargs.get("subject") is not None and kwargs.get("subject") != existing.subject:
            updated_fields.append("subject")
        if kwargs.get("description") is not None and kwargs.get("description") != existing.description:
            updated_fields.append("description")
        if kwargs.get("activeForm") is not None and kwargs.get("activeForm") != existing.active_form:
            updated_fields.append("activeForm")
        if kwargs.get("owner") is not None and kwargs.get("owner") != existing.owner:
            updated_fields.append("owner")
        if status is not None and status != existing.status.value:
            updated_fields.append("status")

        updated_fields = list(dict.fromkeys(updated_fields))
        updated = self._store.update_task(
            task_id,
            subject=kwargs.get("subject"),
            description=kwargs.get("description"),
            active_form=kwargs.get("activeForm"),
            owner=kwargs.get("owner"),
            status=TaskStatus(status) if status and status != "deleted" else None,
            blocks=merged_blocks,
            blocked_by=merged_blocked_by,
            metadata=merged_metadata if metadata is not None else existing.metadata,
        )

        payload = {
            "id": updated.id,
            "subject": updated.subject,
            "description": updated.description,
            "status": updated.status.value,
            "blocks": list(updated.blocks),
            "blockedBy": list(updated.blocked_by),
        }
        ctx = get_current_tool_runtime_context()
        if ctx is not None:
            ctx.task_reads.record(
                TaskReadSnapshot(task_id=task_id, payload=payload, last_action="update")
            )

        content = f"Updated task #{task_id} {', '.join(updated_fields) or 'successfully'}"
        if status == TaskStatus.COMPLETED.value:
            content += (
                "\n\nTask completed. Call TaskList now to find your next available task "
                "or see if your work unblocked others."
            )

        return ToolExecutionResult(
            content=content,
            data={
                "success": True,
                "taskId": task_id,
                "updatedFields": updated_fields,
                "statusChange": (
                    {"from": existing.status.value, "to": updated.status.value}
                    if status is not None and status != existing.status.value
                    else None
                ),
            },
        )
