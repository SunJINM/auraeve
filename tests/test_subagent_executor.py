"""子智能体执行器测试。"""
import pytest
from unittest.mock import MagicMock
from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.subagents.data.models import Task, TaskBudget, TaskStatus
from auraeve.subagents.executor import SubagentExecutor


@pytest.fixture
def store(tmp_path):
    from auraeve.subagents.data.repositories import SubagentStore
    return SubagentStore(str(tmp_path / "test.db"))


@pytest.fixture
def command_queue():
    return RuntimeCommandQueue()


@pytest.fixture
def executor(store, command_queue):
    return SubagentExecutor(
        store=store,
        command_queue=command_queue,
        provider=MagicMock(),
        tool_builder=MagicMock(return_value=MagicMock()),
        policy=MagicMock(),
        model="test-model",
        max_concurrent=3,
    )


def test_executor_init(executor):
    assert executor._max_concurrent == 3
    assert len(executor._running) == 0


def test_create_task(executor):
    task = executor.create_task(
        goal="测试任务",
        agent_type="general-purpose",
        origin_channel="test",
        origin_chat_id="chat1",
        spawn_tool_call_id="call_1",
    )
    assert task.task_id is not None
    assert task.goal == "测试任务"
    assert task.status == TaskStatus.QUEUED

    loaded = executor._store.get_task(task.task_id)
    assert loaded is not None
    assert loaded.goal == "测试任务"


def test_create_task_respects_max_concurrent(executor):
    executor._max_concurrent = 1
    executor._running["fake"] = MagicMock()
    with pytest.raises(RuntimeError, match="并发"):
        executor.create_task(goal="新任务", origin_channel="test", origin_chat_id="c1")


def test_list_tasks(executor):
    executor.create_task(goal="任务1", origin_channel="t", origin_chat_id="c")
    executor.create_task(goal="任务2", origin_channel="t", origin_chat_id="c")
    tasks = executor.list_tasks()
    assert len(tasks) == 2


def test_get_task(executor):
    task = executor.create_task(goal="查询测试", origin_channel="t", origin_chat_id="c")
    loaded = executor.get_task(task.task_id)
    assert loaded is not None
    assert loaded.goal == "查询测试"


def test_cancel_nonexistent(executor):
    assert executor.cancel_task("nonexistent") is False
