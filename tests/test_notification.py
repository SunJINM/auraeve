"""子智能体通知模型测试。"""

from auraeve.subagents.notification import TaskNotification


def _make_notification(**kwargs):
    defaults = dict(
        task_id="t1", agent_type="general-purpose",
        goal="测试", status="completed", result="完成了",
        spawn_tool_call_id="call_123",
    )
    defaults.update(kwargs)
    return TaskNotification(**defaults)


def test_notification_to_payload():
    notification = _make_notification(spawn_tool_call_id="call_456")
    payload = notification.to_payload()

    assert payload["task_id"] == "t1"
    assert payload["status"] == "completed"
    assert payload["spawn_tool_call_id"] == "call_456"
