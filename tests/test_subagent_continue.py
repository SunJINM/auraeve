from unittest.mock import AsyncMock, MagicMock

import pytest

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.subagents.data.models import TaskStatus
from auraeve.subagents.executor import SubagentExecutor


@pytest.fixture
def store(tmp_path):
    from auraeve.subagents.data.repositories import SubagentStore

    return SubagentStore(str(tmp_path / "subagent.db"))


@pytest.fixture
def executor(store, tmp_path):
    return SubagentExecutor(
        store=store,
        command_queue=RuntimeCommandQueue(),
        provider=MagicMock(),
        tool_builder=MagicMock(return_value=MagicMock()),
        policy=MagicMock(),
        model="test-model",
        max_concurrent=3,
        sessions_dir=tmp_path / "sub-sessions",
    )


@pytest.mark.asyncio
async def test_continue_missing_task_returns_error(executor):
    result = await executor.continue_task("missing", "继续")
    assert "未找到任务" in result


@pytest.mark.asyncio
async def test_continue_completed_task_sets_running_before_execution(executor, monkeypatch):
    task = executor.create_task(goal="第一次", origin_channel="t", origin_chat_id="c")
    task.status = TaskStatus.COMPLETED
    executor._store.save_task(task)
    monkeypatch.setattr(executor, "_run_task", AsyncMock(return_value="ok"))

    await executor.continue_task(task.task_id, "继续第二轮")

    loaded = executor.get_task(task.task_id)
    assert loaded is not None
    assert loaded.status == TaskStatus.RUNNING
