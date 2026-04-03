from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from auraeve.agent.legacy_todo_state import extract_latest_todos
from auraeve.agent.tasks import TaskStore


_TASK_V2_NAMES = {"TaskCreate", "TaskGet", "TaskUpdate", "TaskList"}
_TASK_REMINDER_TURNS = 10


def _iter_assistant_tool_names(message: dict[str, Any]) -> list[str]:
    names: list[str] = []
    if message.get("role") != "assistant":
        return names
    for tool_call in message.get("tool_calls") or []:
        function = tool_call.get("function") or {}
        name = str(function.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def _assistant_turns_since(
    messages: list[dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool],
) -> int | None:
    turns = 0
    for message in reversed(messages):
        if message.get("role") != "assistant":
            continue
        if predicate(message):
            return turns
        turns += 1
    return turns if turns > 0 else None


def _has_task_management_tool_call(message: dict[str, Any]) -> bool:
    names = set(_iter_assistant_tool_names(message))
    return bool({"TaskCreate", "TaskUpdate"} & names)


def _has_legacy_todo_tool_call(message: dict[str, Any]) -> bool:
    return "todo" in _iter_assistant_tool_names(message)


def _should_emit_turn_based_reminder(turns_since_management: int | None) -> bool:
    if turns_since_management is None:
        return False
    return (
        turns_since_management >= _TASK_REMINDER_TURNS
        and turns_since_management % _TASK_REMINDER_TURNS == 0
    )


def _format_task_summary(task_base_dir: Path | None, session_key: str) -> str:
    if task_base_dir is None:
        return ""
    tasks = TaskStore(base_dir=task_base_dir, task_list_id=session_key).list_tasks()
    if not tasks:
        return ""
    lines = [
        f"#{task.id}. [{task.status.value}] {task.subject}"
        for task in tasks
    ]
    return "\n\n现有任务：\n" + "\n".join(lines)


def _format_legacy_todo_summary(messages: list[dict[str, Any]]) -> str:
    todos = extract_latest_todos(messages)
    if not todos:
        return ""
    lines = [
        f"{idx}. [{item.get('status')}] {item.get('content')}"
        for idx, item in enumerate(todos, start=1)
    ]
    return "\n\n现有 todo：\n" + "\n".join(lines)


def build_task_runtime_instruction(
    *,
    session_key: str,
    session_messages: list[dict[str, Any]],
    available_tools: set[str],
    task_base_dir: Path | None,
) -> str | None:
    if _TASK_V2_NAMES & available_tools:
        turns_since_management = _assistant_turns_since(
            session_messages,
            _has_task_management_tool_call,
        )
        if not _should_emit_turn_based_reminder(turns_since_management):
            return None
        return (
            "最近没有使用任务工具。如果当前工作确实适合任务跟踪，可考虑使用 TaskCreate 新增任务，"
            "并使用 TaskUpdate 在开始时标记为 in_progress、完成时标记为 completed。"
            "如果任务列表已经陈旧，也可以清理它。仅在与当前工作相关时使用；如果不适用就忽略。"
            "不要向用户提及这条提醒。"
            + _format_task_summary(task_base_dir, session_key)
        )

    if "todo" in available_tools:
        turns_since_management = _assistant_turns_since(
            session_messages,
            _has_legacy_todo_tool_call,
        )
        if not _should_emit_turn_based_reminder(turns_since_management):
            return None
        return (
            "最近没有使用 todo 工具。如果当前工作确实适合任务跟踪，可考虑使用 todo 更新当前计划，"
            "并保持计划与实际进展一致。如果 todo 列表已经陈旧，也可以清理它。"
            "仅在与当前工作相关时使用；如果不适用就忽略。不要向用户提及这条提醒。"
            + _format_legacy_todo_summary(session_messages)
        )

    return None
