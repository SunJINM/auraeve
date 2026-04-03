from __future__ import annotations

from pathlib import Path
from typing import Any

from auraeve.agent.legacy_todo_state import extract_latest_todos
from auraeve.agent.tasks import TaskStore


_TASK_V2_NAMES = {"TaskCreate", "TaskGet", "TaskUpdate", "TaskList"}


def _recent_tool_names(messages: list[dict[str, Any]], window: int = 8) -> set[str]:
    names: set[str] = set()
    for message in messages[-window:]:
        if message.get("role") != "assistant":
            continue
        for tool_call in message.get("tool_calls") or []:
            function = tool_call.get("function") or {}
            name = str(function.get("name") or "").strip()
            if name:
                names.add(name)
    return names


def build_task_runtime_instruction(
    *,
    session_key: str,
    session_messages: list[dict[str, Any]],
    available_tools: set[str],
    task_base_dir: Path | None,
) -> str | None:
    recent_tools = _recent_tool_names(session_messages)

    if _TASK_V2_NAMES & available_tools:
        if task_base_dir is None:
            return None
        store = TaskStore(base_dir=task_base_dir, task_list_id=session_key)
        tasks = store.list_tasks()
        if not tasks:
            return None
        if all(task.status.value == "completed" for task in tasks):
            return None
        if {"TaskCreate", "TaskUpdate"} & recent_tools:
            return None
        return (
            "你当前仍有未完成任务。继续执行前，先用 TaskGet / TaskUpdate 同步最新任务状态，"
            "完成后及时标记 completed，不要向用户提及这条内部提醒。"
        )

    if "todo" in available_tools:
        todos = extract_latest_todos(session_messages)
        if not todos:
            return None
        if not any(str(item.get("status")) in {"pending", "in_progress"} for item in todos):
            return None
        if "todo" in recent_tools:
            return None
        return (
            "你当前仍有未完成的 todo 计划。继续执行前，先调用 todo 更新完整任务列表，"
            "完成后再继续，不要向用户提及这条内部提醒。"
        )

    return None
