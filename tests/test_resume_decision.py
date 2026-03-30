from unittest.mock import MagicMock
import pytest
from auraeve.subagents.data.models import Task, TaskStatus
from auraeve.subagents.control_plane.resume_decision import ResumeDecision, decide_resume


def _make_task(**kwargs) -> Task:
    defaults = dict(task_id="t1", goal="do it", trace_id="", origin_channel="webui", origin_chat_id="chat1")
    defaults.update(kwargs)
    return Task(**defaults)


def test_no_origin_channel_returns_store_only():
    task = _make_task(origin_channel="")
    db = MagicMock()
    result = decide_resume(task, db)
    assert result == ResumeDecision.STORE_ONLY


def test_independent_task_returns_resume_and_reply():
    task = _make_task(trace_id="")
    db = MagicMock()
    result = decide_resume(task, db)
    assert result == ResumeDecision.RESUME_AND_REPLY


def test_dag_with_pending_siblings_returns_wait_for_others():
    task = _make_task(trace_id="trace1")
    sibling_pending = _make_task(task_id="t2", trace_id="trace1", status=TaskStatus.RUNNING)
    sibling_done = _make_task(task_id="t1", trace_id="trace1", status=TaskStatus.COMPLETED)
    db = MagicMock()
    db.list_tasks_by_trace.return_value = [sibling_done, sibling_pending]
    result = decide_resume(task, db)
    assert result == ResumeDecision.WAIT_FOR_OTHERS


def test_dag_all_siblings_done_returns_resume_and_reply():
    task = _make_task(trace_id="trace1")
    s1 = _make_task(task_id="t1", trace_id="trace1", status=TaskStatus.COMPLETED)
    s2 = _make_task(task_id="t2", trace_id="trace1", status=TaskStatus.COMPLETED)
    db = MagicMock()
    db.list_tasks_by_trace.return_value = [s1, s2]
    result = decide_resume(task, db)
    assert result == ResumeDecision.RESUME_AND_REPLY
