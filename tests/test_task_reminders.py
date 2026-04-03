from __future__ import annotations

from pathlib import Path

from auraeve.agent.tasks import TaskStore
from auraeve.agent_runtime.task_reminders import build_task_runtime_instruction


def test_build_task_runtime_instruction_does_not_nag_before_threshold(tmp_path: Path) -> None:
    store = TaskStore(base_dir=tmp_path / "tasks", task_list_id="webui:chat-1")
    store.create_task(subject="实现迁移", description="切换到 Task V2")

    reminder = build_task_runtime_instruction(
        session_key="webui:chat-1",
        session_messages=[
            {"role": "assistant", "content": "a1"},
            {"role": "assistant", "content": "a2"},
            {"role": "assistant", "content": "a3"},
            {"role": "assistant", "content": "a4"},
            {"role": "assistant", "content": "a5"},
            {"role": "assistant", "content": "a6"},
            {"role": "assistant", "content": "a7"},
            {"role": "assistant", "content": "a8"},
            {"role": "assistant", "content": "a9"},
        ],
        available_tools={"TaskCreate", "TaskGet", "TaskUpdate", "TaskList"},
        task_base_dir=tmp_path / "tasks",
    )

    assert reminder is None


def test_build_task_runtime_instruction_for_task_v2_is_gentle_and_turn_based(
    tmp_path: Path,
) -> None:
    store = TaskStore(base_dir=tmp_path / "tasks", task_list_id="webui:chat-1")
    store.create_task(subject="实现迁移", description="切换到 Task V2")

    reminder = build_task_runtime_instruction(
        session_key="webui:chat-1",
        session_messages=[
            {"role": "assistant", "content": "a1"},
            {"role": "assistant", "content": "a2"},
            {"role": "assistant", "content": "a3"},
            {"role": "assistant", "content": "a4"},
            {"role": "assistant", "content": "a5"},
            {"role": "assistant", "content": "a6"},
            {"role": "assistant", "content": "a7"},
            {"role": "assistant", "content": "a8"},
            {"role": "assistant", "content": "a9"},
            {"role": "assistant", "content": "a10"},
        ],
        available_tools={"TaskCreate", "TaskGet", "TaskUpdate", "TaskList"},
        task_base_dir=tmp_path / "tasks",
    )

    assert reminder is not None
    assert "如果当前工作确实适合任务跟踪" in reminder
    assert "仅在与当前工作相关时使用" in reminder
    assert "不要向用户提及这条提醒" in reminder
    assert "TaskCreate" in reminder
    assert "TaskUpdate" in reminder
    assert "先正常回答用户当前消息" not in reminder
    assert "询问用户是否继续" not in reminder
    assert "#1. [pending] 实现迁移" in reminder


def test_build_task_runtime_instruction_skips_when_task_tools_recently_used(tmp_path: Path) -> None:
    store = TaskStore(base_dir=tmp_path / "tasks", task_list_id="webui:chat-1")
    store.create_task(subject="实现迁移", description="切换到 Task V2")

    reminder = build_task_runtime_instruction(
        session_key="webui:chat-1",
        session_messages=[
            {"role": "assistant", "content": "a1"},
            {"role": "assistant", "content": "a2"},
            {"role": "assistant", "content": "a3"},
            {"role": "assistant", "content": "a4"},
            {"role": "assistant", "content": "a5"},
            {"role": "assistant", "content": "a6"},
            {"role": "assistant", "content": "a7"},
            {"role": "assistant", "content": "a8"},
            {"role": "assistant", "content": "a9"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "TaskUpdate", "arguments": "{\"taskId\":\"1\",\"status\":\"in_progress\"}"},
                    }
                ],
            },
        ],
        available_tools={"TaskCreate", "TaskGet", "TaskUpdate", "TaskList"},
        task_base_dir=tmp_path / "tasks",
    )

    assert reminder is None


def test_build_task_runtime_instruction_for_stale_legacy_todo() -> None:
    reminder = build_task_runtime_instruction(
        session_key="napcat:user-1",
        session_messages=[
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "todo",
                            "arguments": (
                                '{"todos":[{"content":"实现迁移","active_form":"正在实现迁移","status":"in_progress"}]}'
                            ),
                        },
                    }
                    ],
                },
            {"role": "user", "content": "继续 1"},
            {"role": "user", "content": "继续 2"},
            {"role": "user", "content": "继续 3"},
            {"role": "user", "content": "继续 4"},
            {"role": "user", "content": "继续 5"},
            {"role": "user", "content": "继续 6"},
            {"role": "user", "content": "继续 7"},
            {"role": "user", "content": "继续 8"},
            {"role": "user", "content": "继续 9"},
        ],
        available_tools={"todo"},
        task_base_dir=None,
    )

    assert reminder is None


def test_build_task_runtime_instruction_for_stale_legacy_todo_after_threshold() -> None:
    reminder = build_task_runtime_instruction(
        session_key="napcat:user-1",
        session_messages=[
            {"role": "assistant", "content": "a1"},
            {"role": "assistant", "content": "a2"},
            {"role": "assistant", "content": "a3"},
            {"role": "assistant", "content": "a4"},
            {"role": "assistant", "content": "a5"},
            {"role": "assistant", "content": "a6"},
            {"role": "assistant", "content": "a7"},
            {"role": "assistant", "content": "a8"},
            {"role": "assistant", "content": "a9"},
            {"role": "assistant", "content": "a10"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "todo",
                            "arguments": (
                                '{"todos":[{"content":"实现迁移","active_form":"正在实现迁移","status":"in_progress"}]}'
                            ),
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "b1"},
            {"role": "assistant", "content": "b2"},
            {"role": "assistant", "content": "b3"},
            {"role": "assistant", "content": "b4"},
            {"role": "assistant", "content": "b5"},
            {"role": "assistant", "content": "b6"},
            {"role": "assistant", "content": "b7"},
            {"role": "assistant", "content": "b8"},
            {"role": "assistant", "content": "b9"},
            {"role": "assistant", "content": "b10"},
        ],
        available_tools={"todo"},
        task_base_dir=None,
    )

    assert reminder is not None
    assert "TodoWrite" not in reminder
    assert "todo" in reminder
    assert "仅在与当前工作相关时使用" in reminder
    assert "不要向用户提及这条提醒" in reminder
