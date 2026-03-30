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
