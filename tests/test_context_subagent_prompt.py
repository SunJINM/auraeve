from pathlib import Path

from auraeve.agent.context import ContextBuilder


def test_subagent_prompt_explains_task_notification_semantics() -> None:
    builder = ContextBuilder(Path("."))

    prompt = builder.build_system_prompt(
        available_tools={"agent"},
        prompt_mode="full",
    )

    assert "task-notification" in prompt
    assert "不是用户新的发言" in prompt
    assert "不要回复“收到”" in prompt
