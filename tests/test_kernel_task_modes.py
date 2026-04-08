from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from auraeve.agent.tools.registry import ToolRegistry
from auraeve.agent_runtime.kernel import RuntimeKernel
from auraeve.session.manager import SessionManager


def test_resolve_runtime_tools_uses_task_v2_for_interactive_channel(tmp_path: Path) -> None:
    kernel = object.__new__(RuntimeKernel)
    kernel.tools = ToolRegistry()
    kernel._plan = MagicMock()
    kernel._task_base_dir = tmp_path / "tasks"

    registry = RuntimeKernel._resolve_runtime_tools(
        kernel,
        channel="webui",
        chat_id="chat-1",
        thread_id="webui:chat-1",
    )

    assert registry.has("TaskCreate")
    assert registry.has("todo") is False


def test_resolve_runtime_tools_uses_legacy_todo_for_non_interactive_channel(tmp_path: Path) -> None:
    kernel = object.__new__(RuntimeKernel)
    kernel.tools = ToolRegistry()
    kernel._plan = MagicMock()
    kernel._task_base_dir = tmp_path / "tasks"

    registry = RuntimeKernel._resolve_runtime_tools(
        kernel,
        channel="napcat",
        chat_id="chat-1",
        thread_id="napcat:user-1",
    )

    assert registry.has("todo")
    assert registry.has("TaskCreate") is False


@pytest.mark.asyncio
async def test_process_message_uses_runtime_tool_registry_without_plan_injection(tmp_path: Path) -> None:
    kernel = object.__new__(RuntimeKernel)
    kernel._media_runtime = None
    kernel._plan = MagicMock()
    kernel._set_media_understand_context = MagicMock()
    kernel._extract_attachments_legacy = AsyncMock(return_value=None)
    kernel._inject_plan_into_messages = MagicMock(side_effect=AssertionError("should not inject plan"))
    kernel._sanitize_assistant_output = RuntimeKernel._sanitize_assistant_output
    kernel.sessions = MagicMock()
    session = MagicMock()
    session.key = "webui:chat-1"
    session.get_history.return_value = []
    kernel.sessions.get_or_create.return_value = session
    runtime_tools = ToolRegistry()
    kernel._resolve_runtime_tools = MagicMock(return_value=runtime_tools)
    kernel._set_tool_context = MagicMock()
    kernel.assembler = MagicMock()
    kernel.assembler.assemble = AsyncMock(
        return_value=MagicMock(messages=[{"role": "system", "content": "你是助手"}], compacted_messages=None, estimated_tokens=0)
    )
    kernel._orchestrator = MagicMock()
    kernel._orchestrator.run = AsyncMock(
        return_value=MagicMock(final_content="ok", tools_used=[], recovery_actions=[], messages=[])
    )
    kernel.hooks = MagicMock(
        run_session_start=AsyncMock(),
        run_session_end=AsyncMock(),
        run_message_sending=AsyncMock(return_value=MagicMock(cancel=False, content="ok")),
    )
    kernel.engine = MagicMock(after_turn=AsyncMock())
    kernel.memory_lifecycle = None
    kernel.model = "model"
    kernel.temperature = 0.0
    kernel.max_tokens = 1000

    await RuntimeKernel._process_message(
        kernel,
        session_key="webui:chat-1",
        channel="webui",
        sender_id="user-1",
        chat_id="chat-1",
        content="hello",
        metadata={},
    )

    assert kernel._inject_plan_into_messages.call_count == 0
    assemble_kwargs = kernel.assembler.assemble.await_args.kwargs
    assert assemble_kwargs["available_tools"] == set(runtime_tools.tool_names)
    kernel._orchestrator.run.assert_awaited_once()
    assert kernel._orchestrator.run.await_args.kwargs["tools"] is runtime_tools


@pytest.mark.asyncio
async def test_process_message_persists_tool_transcript_messages(tmp_path: Path) -> None:
    kernel = object.__new__(RuntimeKernel)
    kernel._media_runtime = None
    kernel._plan = MagicMock()
    kernel._set_media_understand_context = MagicMock()
    kernel._extract_attachments_legacy = AsyncMock(return_value=None)
    kernel._sanitize_assistant_output = RuntimeKernel._sanitize_assistant_output
    kernel.sessions = SessionManager(tmp_path / "sessions")
    kernel._resolve_runtime_tools = MagicMock(return_value=ToolRegistry())
    kernel._set_tool_context = MagicMock()
    kernel.assembler = MagicMock()
    kernel.assembler.assemble = AsyncMock(
        return_value=MagicMock(messages=[{"role": "system", "content": "你是助手"}], compacted_messages=None, estimated_tokens=0)
    )
    kernel._orchestrator = MagicMock()
    kernel._orchestrator.run = AsyncMock(
        return_value=MagicMock(
            final_content="完成",
            tools_used=["todo"],
            recovery_actions=[],
            messages=[
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "todo", "arguments": "{\"todos\":[]}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call-1", "name": "todo", "content": "已清空"},
            ],
        )
    )
    kernel.hooks = MagicMock(
        run_session_start=AsyncMock(),
        run_session_end=AsyncMock(),
        run_message_sending=AsyncMock(return_value=MagicMock(cancel=False, content="完成")),
    )
    kernel.engine = MagicMock(after_turn=AsyncMock())
    kernel.memory_lifecycle = None
    kernel.model = "model"
    kernel.temperature = 0.0
    kernel.max_tokens = 1000

    await RuntimeKernel._process_message(
        kernel,
        session_key="napcat:user-1",
        channel="napcat",
        sender_id="user-1",
        chat_id="user-1",
        content="请完成任务",
        metadata={},
    )

    session = kernel.sessions.get_or_create("napcat:user-1")
    assert any(item.get("role") == "assistant" and item.get("tool_calls") for item in session.messages)
    assert any(item.get("role") == "tool" and item.get("name") == "todo" for item in session.messages)
