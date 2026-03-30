import pytest
from auraeve.subagents.control_plane.pending_results import PendingResultStore


def test_add_and_is_complete_false_when_pending():
    store = PendingResultStore()
    store.add("trace1", "task1", {"status": "success", "summary": "ok"})
    assert not store.is_complete("trace1", total=2)


def test_is_complete_true_when_all_added():
    store = PendingResultStore()
    store.add("trace1", "task1", {"status": "success", "summary": "a"})
    store.add("trace1", "task2", {"status": "success", "summary": "b"})
    assert store.is_complete("trace1", total=2)


def test_collect_and_clear():
    store = PendingResultStore()
    store.add("trace1", "task1", {"summary": "a"})
    store.add("trace1", "task2", {"summary": "b"})
    results = store.collect_and_clear("trace1")
    assert len(results) == 2
    assert store.is_complete("trace1", total=0)  # cleared


def test_idempotent_add():
    store = PendingResultStore()
    store.add("trace1", "task1", {"summary": "a"})
    store.add("trace1", "task1", {"summary": "b"})  # 重复 task_id
    results = store.collect_and_clear("trace1")
    assert len(results) == 1  # 只存一条
