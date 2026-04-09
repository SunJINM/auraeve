from unittest.mock import MagicMock

from auraeve.subagents.data.models import Task, TaskBudget
from auraeve.subagents.runtime.react_loop import ReActLoop


def test_build_messages_for_fresh_task_starts_with_system_and_user():
    loop = ReActLoop(
        provider=MagicMock(),
        tools=MagicMock(),
        policy=MagicMock(),
        model="test-model",
    )
    task = Task(
        task_id="task-fresh",
        goal="分析代码",
        budget=TaskBudget(),
    )

    messages = loop._prepare_messages(task, history_messages=[])  # noqa: SLF001

    assert messages[0]["role"] == "system"
    assert messages[-1] == {"role": "user", "content": "分析代码"}


def test_build_messages_for_inherit_task_keeps_seed_history():
    loop = ReActLoop(
        provider=MagicMock(),
        tools=MagicMock(),
        policy=MagicMock(),
        model="test-model",
    )
    task = Task(
        task_id="task-fork",
        goal="继续检查这个方向",
        context_mode="inherit",
        execution_mode="fork",
        budget=TaskBudget(),
    )

    messages = loop._prepare_messages(  # noqa: SLF001
        task,
        history_messages=[{"role": "assistant", "content": "之前的结论"}],
    )

    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "之前的结论"
    assert messages[-1]["content"] == "继续检查这个方向"
