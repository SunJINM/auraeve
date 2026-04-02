from auraeve.agent_runtime.command_projection import project_command_to_messages
from auraeve.agent_runtime.command_types import QueuedCommand


def test_task_notification_projects_to_background_event_message() -> None:
    command = QueuedCommand(
        id="n1",
        session_key="s1",
        source="subagent",
        mode="task-notification",
        priority="later",
        payload={
            "task_id": "task-1",
            "agent_type": "general-purpose",
            "goal": "collect facts",
            "status": "completed",
            "result": "done",
        },
        origin={"kind": "task-notification"},
    )

    messages = project_command_to_messages(command)

    assert messages[0]["role"] == "user"
    assert "background agent completed a task" in messages[0]["content"]
    assert "task-1" in messages[0]["content"]


def test_prompt_projects_to_plain_user_message() -> None:
    command = QueuedCommand(
        id="p1",
        session_key="s1",
        source="terminal",
        mode="prompt",
        priority="next",
        payload={"content": "hello"},
        origin={"kind": "user"},
    )

    messages = project_command_to_messages(command)

    assert messages == [{"role": "user", "content": "hello"}]
