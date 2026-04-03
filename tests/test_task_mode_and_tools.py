from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from auraeve.agent.context import ContextBuilder
from auraeve.agent.tools.assembler import build_tool_registry
from auraeve.agent_runtime.task_mode import is_task_v2_enabled


def test_task_v2_enabled_for_interactive_channels_by_default() -> None:
    assert is_task_v2_enabled(channel="webui") is True
    assert is_task_v2_enabled(channel="terminal") is True


def test_task_v2_disabled_for_non_interactive_channels_by_default() -> None:
    assert is_task_v2_enabled(channel="napcat") is False
    assert is_task_v2_enabled(channel="dingtalk") is False
    assert is_task_v2_enabled(channel="cron") is False


def test_task_v2_disabled_for_subagents_by_default() -> None:
    assert is_task_v2_enabled(channel="webui", is_subagent=True) is False


def test_task_v2_env_override_forces_enable() -> None:
    assert is_task_v2_enabled(
        channel="napcat",
        env={"AURAEVE_ENABLE_TASKS": "1"},
    ) is True


def test_build_tool_registry_registers_task_v2_tools_without_legacy_todo(tmp_path: Path) -> None:
    registry = build_tool_registry(
        profile="main",
        workspace=tmp_path,
        restrict_to_workspace=False,
        exec_timeout=5,
        brave_api_key=None,
        bus_publish_outbound=AsyncMock(),
        provider=MagicMock(),
        model="test-model",
        plan_manager=MagicMock(),
        task_mode="task_v2",
        task_session_key="webui:chat-1",
    )

    assert registry.has("TaskCreate")
    assert registry.has("TaskGet")
    assert registry.has("TaskUpdate")
    assert registry.has("TaskList")
    assert registry.has("todo") is False


def test_build_tool_registry_registers_legacy_todo_without_task_v2_tools(tmp_path: Path) -> None:
    registry = build_tool_registry(
        profile="main",
        workspace=tmp_path,
        restrict_to_workspace=False,
        exec_timeout=5,
        brave_api_key=None,
        bus_publish_outbound=AsyncMock(),
        provider=MagicMock(),
        model="test-model",
        plan_manager=MagicMock(),
        task_mode="legacy_todo",
        task_session_key="napcat:user-1",
    )

    assert registry.has("todo")
    assert registry.has("TaskCreate") is False
    assert registry.has("TaskGet") is False
    assert registry.has("TaskUpdate") is False
    assert registry.has("TaskList") is False


def test_context_builder_prefers_task_v2_guidance_over_legacy_todo(tmp_path: Path) -> None:
    builder = ContextBuilder(tmp_path)

    prompt = builder.build_system_prompt(
        channel="webui",
        chat_id="chat-1",
        available_tools={"TaskCreate", "TaskGet", "TaskUpdate", "TaskList"},
    )

    assert "TaskCreate" in prompt
    assert "TaskUpdate" in prompt
    assert "复杂任务（3 步以上）先调用 todo 建立计划" not in prompt


def test_context_builder_keeps_legacy_todo_guidance_when_only_todo_available(tmp_path: Path) -> None:
    builder = ContextBuilder(tmp_path)

    prompt = builder.build_system_prompt(
        channel="napcat",
        chat_id="chat-1",
        available_tools={"todo"},
    )

    assert "复杂任务（3 步以上）先调用 todo 建立计划" in prompt
    assert "TaskCreate" not in prompt
