"""子智能体数据模型测试。"""
from auraeve.subagents.data.models import (
    Task, TaskBudget, TaskStatus, ProgressTracker,
    TERMINAL_STATUSES, is_terminal, is_valid_transition,
    STATUS_ICON,
)


def test_task_default_values():
    t = Task(task_id="abc123", goal="测试任务")
    assert t.task_id == "abc123"
    assert t.goal == "测试任务"
    assert t.agent_type == "general-purpose"
    assert t.status == TaskStatus.QUEUED
    assert t.priority == 5
    assert t.run_in_background is True
    assert t.budget.max_steps == 50
    assert t.budget.max_duration_s == 600
    assert t.budget.max_tool_calls == 100


def test_task_budget_custom():
    b = TaskBudget(max_steps=20, max_duration_s=120, max_tool_calls=50)
    assert b.max_steps == 20
    assert b.max_duration_s == 120
    assert b.max_tool_calls == 50


def test_terminal_statuses():
    assert is_terminal(TaskStatus.COMPLETED) is True
    assert is_terminal(TaskStatus.FAILED) is True
    assert is_terminal(TaskStatus.KILLED) is True
    assert is_terminal(TaskStatus.RUNNING) is False
    assert is_terminal(TaskStatus.QUEUED) is False


def test_valid_transitions():
    assert is_valid_transition(TaskStatus.QUEUED, TaskStatus.RUNNING) is True
    assert is_valid_transition(TaskStatus.RUNNING, TaskStatus.COMPLETED) is True
    assert is_valid_transition(TaskStatus.RUNNING, TaskStatus.FAILED) is True
    assert is_valid_transition(TaskStatus.RUNNING, TaskStatus.KILLED) is True
    assert is_valid_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING) is False
    assert is_valid_transition(TaskStatus.QUEUED, TaskStatus.COMPLETED) is False


def test_progress_tracker():
    p = ProgressTracker()
    assert p.tool_use_count == 0
    assert p.total_tokens == 0
    assert p.recent_activities == []
    assert p.duration_ms == 0


def test_progress_tracker_record():
    p = ProgressTracker()
    p.record_activity("Read", {"file_path": "foo.py"})
    assert p.tool_use_count == 1
    assert len(p.recent_activities) == 1
    # 超过5个时自动淘汰旧的
    for i in range(6):
        p.record_activity("Bash", {"cmd": f"cmd{i}"})
    assert len(p.recent_activities) == 5


def test_status_icons():
    assert STATUS_ICON[TaskStatus.QUEUED] == "⏳"
    assert STATUS_ICON[TaskStatus.RUNNING] == "🔄"
    assert STATUS_ICON[TaskStatus.COMPLETED] == "✅"
    assert STATUS_ICON[TaskStatus.FAILED] == "❌"
    assert STATUS_ICON[TaskStatus.KILLED] == "⚫"
