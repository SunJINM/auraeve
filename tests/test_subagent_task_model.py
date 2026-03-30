# tests/test_subagent_task_model.py
import pytest
from auraeve.subagents.data.models import Task


def test_task_has_spawn_tool_call_id_field():
    t = Task(task_id="t1", goal="do something")
    assert t.spawn_tool_call_id == ""


def test_task_has_agent_name_field():
    t = Task(task_id="t1", goal="do something")
    assert t.agent_name == ""


def test_task_agent_name_can_be_set():
    t = Task(task_id="t1", goal="do something", agent_name="data_analyst_agent")
    assert t.agent_name == "data_analyst_agent"


import tempfile
import os
from pathlib import Path
from auraeve.subagents.data.repositories import SubagentDB


def test_task_roundtrip_with_new_fields():
    """验证 spawn_tool_call_id 和 agent_name 能正确写入和读取。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = SubagentDB(Path(tmpdir) / "test.db")
        try:
            task = Task(
                task_id="rt1",
                goal="round-trip test",
                spawn_tool_call_id="call_abc123",
                agent_name="data_analyst_agent",
            )
            db.save_task(task)
            loaded = db.get_task("rt1")
            assert loaded is not None
            assert loaded.spawn_tool_call_id == "call_abc123"
            assert loaded.agent_name == "data_analyst_agent"
        finally:
            db.close()


def test_task_roundtrip_empty_new_fields():
    """验证新字段默认值空字符串能正确持久化。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = SubagentDB(Path(tmpdir) / "test.db")
        try:
            task = Task(task_id="rt2", goal="empty fields test")
            db.save_task(task)
            loaded = db.get_task("rt2")
            assert loaded is not None
            assert loaded.spawn_tool_call_id == ""
            assert loaded.agent_name == ""
        finally:
            db.close()
