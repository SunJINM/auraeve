from __future__ import annotations

import json
from pathlib import Path

import pytest

from auraeve.agent.tasks import TaskStatus, TaskStore
from auraeve.agent.tools.base import ToolExecutionResult
from auraeve.agent.tools.task_create import TaskCreateTool
from auraeve.agent.tools.task_get import TASK_UNCHANGED_STUB, TaskGetTool
from auraeve.agent.tools.task_list import TaskListTool
from auraeve.agent.tools.task_update import TaskUpdateTool
from auraeve.agent_runtime.tool_runtime_context import (
    FileReadStateStore,
    TaskReadStateStore,
    ToolRuntimeContext,
    use_tool_runtime_context,
)


@pytest.mark.asyncio
async def test_task_list_returns_summary_and_filters_completed_blockers(
    tmp_path: Path,
) -> None:
    store = TaskStore(base_dir=tmp_path / "tasks", task_list_id="webui:chat-1")
    first = store.create_task(
        subject="基础设施",
        description="先完成基础设施",
        status=TaskStatus.COMPLETED,
    )
    second = store.create_task(
        subject="实现功能",
        description="实现主要功能",
        blocked_by=[first.id],
    )
    third = store.create_task(
        subject="回归验证",
        description="做回归验证",
        blocked_by=[second.id],
        owner="eve",
        status=TaskStatus.IN_PROGRESS,
    )

    tool = TaskListTool(store)
    result = await tool.execute()

    assert isinstance(result, ToolExecutionResult)
    assert result.data["tasks"][1]["blockedBy"] == []
    assert result.data["tasks"][2]["blockedBy"] == [second.id]
    assert "#2 [pending] 实现功能" in result.content
    assert "#3 [in_progress] 回归验证 (eve) [blocked by #2]" in result.content


@pytest.mark.asyncio
async def test_task_update_completed_nudges_to_task_list(
    tmp_path: Path,
) -> None:
    store = TaskStore(base_dir=tmp_path / "tasks", task_list_id="webui:chat-1")
    task = store.create_task(subject="实现功能", description="实现主要功能")
    tool = TaskUpdateTool(store)

    result = await tool.execute(taskId=task.id, status="completed")

    assert isinstance(result, ToolExecutionResult)
    assert result.data["success"] is True
    assert result.data["statusChange"] == {"from": "pending", "to": "completed"}
    assert "Task completed. Call TaskList now" in result.content


@pytest.mark.asyncio
async def test_task_get_returns_unchanged_stub_after_same_turn_update(
    tmp_path: Path,
) -> None:
    store = TaskStore(base_dir=tmp_path / "tasks", task_list_id="webui:chat-1")
    task = store.create_task(subject="实现功能", description="实现主要功能")
    get_tool = TaskGetTool(store)
    update_tool = TaskUpdateTool(store)
    ctx = ToolRuntimeContext(
        file_reads=FileReadStateStore(),
        task_reads=TaskReadStateStore(),
    )

    with use_tool_runtime_context(ctx):
        update_result = await update_tool.execute(taskId=task.id, status="in_progress")
        get_result = await get_tool.execute(taskId=task.id)

    assert isinstance(update_result, ToolExecutionResult)
    assert isinstance(get_result, ToolExecutionResult)
    assert get_result.content == TASK_UNCHANGED_STUB


@pytest.mark.asyncio
async def test_task_create_returns_short_confirmation_payload(
    tmp_path: Path,
) -> None:
    store = TaskStore(base_dir=tmp_path / "tasks", task_list_id="webui:chat-1")
    tool = TaskCreateTool(store)

    result = await tool.execute(subject="实现功能", description="实现主要功能")

    assert isinstance(result, ToolExecutionResult)
    assert result.data["task"]["subject"] == "实现功能"
    assert "created successfully" in result.content.lower()


@pytest.mark.asyncio
async def test_task_create_starts_a_fresh_list_after_completed_tasks(
    tmp_path: Path,
) -> None:
    store = TaskStore(base_dir=tmp_path / "tasks", task_list_id="webui:chat-1")
    store.create_task(subject="旧任务", description="上一轮任务")
    store.update_task("1", status=TaskStatus.COMPLETED)
    task_path = store.directory / "1.json"
    payload = json.loads(task_path.read_text(encoding="utf-8"))
    payload["updated_at"] = "2020-01-01T00:00:00+00:00"
    task_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tool = TaskCreateTool(store)

    result = await tool.execute(subject="新任务", description="下一轮任务")

    assert isinstance(result, ToolExecutionResult)
    assert result.data["task"]["id"] == "2"
    tasks = store.list_tasks()
    assert len(tasks) == 1
    assert tasks[0].id == "2"
    assert tasks[0].subject == "新任务"
