"""通知队列测试。"""
import json
from auraeve.subagents.notification import (
    NotificationQueue,
    TaskNotification,
)


def _make_notification(**kwargs):
    defaults = dict(
        task_id="t1", agent_type="general-purpose",
        goal="测试", status="completed", result="完成了",
        spawn_tool_call_id="call_123",
    )
    defaults.update(kwargs)
    return TaskNotification(**defaults)


def test_enqueue_and_drain():
    q = NotificationQueue()
    q.enqueue(_make_notification())
    assert q.pending_count == 1
    notifications = q.drain()
    assert len(notifications) == 1
    assert notifications[0].task_id == "t1"
    assert q.pending_count == 0


def test_drain_empty():
    q = NotificationQueue()
    assert q.drain() == []


def test_build_synthetic_messages():
    n = _make_notification(spawn_tool_call_id="call_456")
    msgs = NotificationQueue.build_synthetic_messages(n)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "assistant"
    assert msgs[0]["tool_calls"][0]["id"] == "call_456"
    assert msgs[1]["role"] == "tool"
    assert msgs[1]["tool_call_id"] == "call_456"
    content = json.loads(msgs[1]["content"])
    assert content["status"] == "completed"


def test_multiple_enqueue_order():
    q = NotificationQueue()
    for i in range(3):
        q.enqueue(_make_notification(task_id=f"t{i}"))
    notifications = q.drain()
    assert [n.task_id for n in notifications] == ["t0", "t1", "t2"]


def test_has_pending():
    q = NotificationQueue()
    assert q.has_pending is False
    q.enqueue(_make_notification())
    assert q.has_pending is True
