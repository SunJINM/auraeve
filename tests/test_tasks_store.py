from __future__ import annotations

from pathlib import Path

from auraeve.agent.tasks import TaskStatus, TaskStore


def test_task_store_creates_persistent_tasks(tmp_path: Path) -> None:
    store = TaskStore(base_dir=tmp_path / "tasks", task_list_id="webui_chat_1")

    created = store.create_task(
        subject="梳理任务分轨",
        description="确认交互式与非交互式入口",
        active_form="正在梳理任务分轨",
    )

    assert created.id == "1"
    assert created.status == TaskStatus.PENDING
    assert (tmp_path / "tasks" / "webui_chat_1" / "1.json").exists()


def test_task_store_updates_task_incrementally(tmp_path: Path) -> None:
    store = TaskStore(base_dir=tmp_path / "tasks", task_list_id="webui_chat_1")
    created = store.create_task(subject="迁移任务", description="实现 Task V2")

    updated = store.update_task(
        task_id=created.id,
        status=TaskStatus.IN_PROGRESS,
        owner="main",
        blocked_by=["2"],
    )

    assert updated.status == TaskStatus.IN_PROGRESS
    assert updated.owner == "main"
    assert updated.blocked_by == ["2"]
    assert store.get_task(created.id).status == TaskStatus.IN_PROGRESS


def test_task_store_lists_tasks_in_id_order(tmp_path: Path) -> None:
    store = TaskStore(base_dir=tmp_path / "tasks", task_list_id="webui_chat_1")
    store.create_task(subject="第二步", description="B")
    store.create_task(subject="第三步", description="C")
    store.create_task(subject="第一步", description="A")

    tasks = store.list_tasks()

    assert [task.id for task in tasks] == ["1", "2", "3"]


def test_task_store_preserves_high_water_mark_after_delete(tmp_path: Path) -> None:
    store = TaskStore(base_dir=tmp_path / "tasks", task_list_id="webui_chat_1")
    first = store.create_task(subject="旧任务", description="A")
    store.delete_task(first.id)

    second = store.create_task(subject="新任务", description="B")

    assert second.id == "2"


def test_task_store_reloads_from_disk(tmp_path: Path) -> None:
    base_dir = tmp_path / "tasks"
    store = TaskStore(base_dir=base_dir, task_list_id="webui_chat_1")
    created = store.create_task(subject="持久化", description="从磁盘恢复")

    reloaded = TaskStore(base_dir=base_dir, task_list_id="webui_chat_1")
    task = reloaded.get_task(created.id)

    assert task is not None
    assert task.subject == "持久化"
