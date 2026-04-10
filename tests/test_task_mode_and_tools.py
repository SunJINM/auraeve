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
    assert registry.has("Bash")
    assert registry.has("message") is False
    assert registry.has("browser") is False
    assert registry.has("exec") is False
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
    assert registry.has("Bash")
    assert registry.has("message") is False
    assert registry.has("browser") is False
    assert registry.has("exec") is False
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


def test_context_builder_uses_read_write_tool_names_without_removed_tools(tmp_path: Path) -> None:
    builder = ContextBuilder(tmp_path)

    prompt = builder.build_system_prompt(
        channel="webui",
        chat_id="chat-1",
        available_tools={"Read", "Write", "Edit", "Bash"},
    )

    assert "- Read: 读取文件内容" in prompt
    assert "- Write: 创建或覆盖文件" in prompt
    assert "- Edit: 精确编辑文件片段" in prompt
    assert "- Bash: 执行 Bash Shell 命令" in prompt
    assert "高风险操作（Bash / Write / Edit）先用一句话说明再执行。" in prompt
    assert "为了高质量完成任务，积极使用最能提升结论质量的工具组合" in prompt
    assert "需要长时间运行且不必立刻读取结果时，使用 run_in_background" in prompt
    assert "每次调用都应明显减少不确定性" in prompt
    assert "若后续可能修改文件，第一次就完整 Read" in prompt
    assert "只有彼此独立、互不依赖的只读工具调用，才应并发发出" in prompt
    assert "依赖前一步结果的调用必须串行执行" in prompt
    assert "多个依赖顺序明确的 Bash 步骤，应合并为一次 Bash 调用并使用 && 串联" in prompt
    assert "Read 读取该技能的 <location>" in prompt
    assert "使用 <location> 字段中的原始路径调用 Read" in prompt
    assert "用 Write 在" in prompt
    assert "默认给出清晰、详细、结构化的答复" in prompt
    assert "不要为了显得详细而堆砌无关内容" in prompt
    assert "禁止因为篇幅考虑把关键事实简单压缩成简版" in prompt
    assert "工具返回内容较长时，禁止截断后假装完整掌握" in prompt
    assert "可分多轮继续读取" in prompt
    assert "写入 docs/ 下的 Markdown 文件" in prompt
    assert "先告知用户文件路径，再提供摘要" in prompt
    assert "message(content=" not in prompt
    assert "以下情况必须调用 message 工具" not in prompt
    assert "- browser:" not in prompt
    assert "list_dir" not in prompt
    assert "- pdf:" not in prompt
    assert "read_file" not in prompt
    assert "write_file" not in prompt
    assert "edit_file" not in prompt
    assert "exec" not in prompt
