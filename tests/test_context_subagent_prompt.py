from pathlib import Path

from auraeve.agent.context import ContextBuilder
from auraeve.subagents.data.models import Task, TaskBudget
from auraeve.subagents.runtime.react_loop import ReActLoop


def test_subagent_prompt_explains_task_notification_semantics() -> None:
    builder = ContextBuilder(Path("."))

    prompt = builder.build_system_prompt(
        available_tools={"agent"},
        prompt_mode="full",
    )

    assert "task-notification" in prompt
    assert "不是用户新的发言" in prompt
    assert "不要回复“收到”" in prompt
    assert "同步前台" in prompt
    assert "后台异步" in prompt
    assert "fork" in prompt
    assert "继续已有子智能体" in prompt


def test_subagent_prompt_includes_tool_efficiency_protocol() -> None:
    loop = ReActLoop(
        provider=object(),
        tools=object(),
        policy=object(),
        model="test-model",
    )
    task = Task(
        task_id="task-1",
        goal="分析仓库结构",
        budget=TaskBudget(max_steps=12, max_tool_calls=20, max_duration_s=60),
    )

    prompt = loop._build_system_prompt(task)  # noqa: SLF001

    assert "优先使用专用工具而不是 Bash" in prompt
    assert "默认优先一次高信息量调用，而不是多次试探性小调用" in prompt
    assert "只有彼此独立、互不依赖的只读工具调用，才应并发发出" in prompt
    assert "依赖前一步结果的调用必须串行执行" in prompt
