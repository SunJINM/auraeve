"""子智能体数据存储测试。"""
import pytest
from auraeve.subagents.data.models import Task, TaskBudget, TaskStatus
from auraeve.subagents.data.repositories import SubagentStore


@pytest.fixture
def store(tmp_path):
    return SubagentStore(str(tmp_path / "test.db"))


def test_save_and_get_task(store):
    task = Task(task_id="t1", goal="测试任务")
    store.save_task(task)
    loaded = store.get_task("t1")
    assert loaded is not None
    assert loaded.task_id == "t1"
    assert loaded.goal == "测试任务"
    assert loaded.agent_type == "general-purpose"
    assert loaded.status == TaskStatus.QUEUED


def test_get_nonexistent_task(store):
    assert store.get_task("nonexistent") is None


def test_update_task_status(store):
    task = Task(task_id="t2", goal="状态测试")
    store.save_task(task)
    store.update_task_status("t2", TaskStatus.RUNNING)
    loaded = store.get_task("t2")
    assert loaded.status == TaskStatus.RUNNING


def test_list_tasks(store):
    store.save_task(Task(task_id="a1", goal="任务A"))
    store.save_task(Task(task_id="a2", goal="任务B"))
    t = Task(task_id="a3", goal="任务C")
    t.status = TaskStatus.RUNNING
    store.save_task(t)

    all_tasks = store.list_tasks()
    assert len(all_tasks) == 3

    running = store.list_tasks(status=TaskStatus.RUNNING)
    assert len(running) == 1
    assert running[0].task_id == "a3"


def test_get_running_count(store):
    store.save_task(Task(task_id="r1", goal="运行中1"))
    store.update_task_status("r1", TaskStatus.RUNNING)
    store.save_task(Task(task_id="r2", goal="运行中2"))
    store.update_task_status("r2", TaskStatus.RUNNING)
    store.save_task(Task(task_id="r3", goal="排队中"))
    assert store.get_running_count() == 2


def test_complete_task(store):
    task = Task(task_id="c1", goal="完成测试")
    store.save_task(task)
    store.update_task_status("c1", TaskStatus.RUNNING)
    store.complete_task("c1", result="完成了", completed_at=1000.0)
    loaded = store.get_task("c1")
    assert loaded.status == TaskStatus.COMPLETED
    assert loaded.result == "完成了"
    assert loaded.completed_at == 1000.0
