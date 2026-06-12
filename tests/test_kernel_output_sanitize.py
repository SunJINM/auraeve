from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auraeve.agent_runtime.kernel import RuntimeKernel
from auraeve.providers.base import LLMResponse


def test_sanitize_drops_mixed_silent_token_line() -> None:
    raw = "抱歉哥！再试一次～\n\n__SILENT__"
    cleaned = RuntimeKernel._sanitize_assistant_output(raw)
    assert cleaned == "抱歉哥！再试一次～"


def test_sanitize_exact_silent_becomes_none() -> None:
    assert RuntimeKernel._sanitize_assistant_output("__SILENT__") is None


def test_sanitize_exact_heartbeat_becomes_none() -> None:
    assert RuntimeKernel._sanitize_assistant_output("HEARTBEAT_OK") is None


@pytest.mark.asyncio
async def test_prompt_message_does_not_silently_drop_control_token(tmp_path: Path) -> None:
    kernel = object.__new__(RuntimeKernel)
    kernel._set_tool_context = MagicMock()
    kernel._extract_attachments_legacy = AsyncMock(return_value=None)
    kernel._sanitize_assistant_output = RuntimeKernel._sanitize_assistant_output
    kernel.sessions = MagicMock()
    session = MagicMock()
    session.key = "webui:chat-1"
    session.get_history.return_value = []
    kernel.sessions.get_or_create.return_value = session
    kernel._resolve_runtime_tools = MagicMock(return_value=MagicMock(tool_names=[]))
    kernel.assembler = MagicMock()
    kernel.assembler.assemble = AsyncMock(
        return_value=MagicMock(messages=[], compacted_messages=None, estimated_tokens=0)
    )
    kernel._orchestrator = MagicMock()
    kernel._orchestrator.run = AsyncMock(
        return_value=MagicMock(final_content="__SILENT__", tools_used=[], recovery_actions=[], messages=[])
    )
    kernel.hooks = MagicMock(
        run_session_start=AsyncMock(),
        run_session_end=AsyncMock(),
        run_message_sending=AsyncMock(return_value=MagicMock(cancel=False, content=None)),
    )
    kernel.engine = MagicMock(after_turn=AsyncMock())
    kernel.memory_lifecycle = None
    kernel.model = "model"
    kernel.temperature = 0.0
    kernel.max_tokens = 1000

    with patch("auraeve.agent_runtime.kernel.logger.warning") as warning_mock:
        result = await RuntimeKernel._process_message(
            kernel,
            session_key="webui:chat-1",
            channel="webui",
            sender_id="user-1",
            chat_id="chat-1",
            content="你好",
            metadata={"command_mode": "prompt"},
        )

    assert result is not None
    assert result.content == "我这边没有生成可发送的回复，请再试一次。"
    warning_mock.assert_called_once()
    warning_message = warning_mock.call_args.args[0]
    assert "模型返回了空回复" in warning_message
    assert "command_mode=prompt" in warning_message
    assert "rawLength=10" in warning_message
    assert "__SILENT__" not in warning_message


@pytest.mark.asyncio
async def test_heartbeat_meta_event_can_stay_silent(tmp_path: Path) -> None:
    kernel = object.__new__(RuntimeKernel)
    kernel._set_tool_context = MagicMock()
    kernel._extract_attachments_legacy = AsyncMock(return_value=None)
    kernel._sanitize_assistant_output = RuntimeKernel._sanitize_assistant_output
    kernel.sessions = MagicMock()
    session = MagicMock()
    session.key = "webui:chat-1"
    session.get_history.return_value = []
    kernel.sessions.get_or_create.return_value = session
    kernel._resolve_runtime_tools = MagicMock(return_value=MagicMock(tool_names=[]))
    kernel.assembler = MagicMock()
    kernel.assembler.assemble = AsyncMock(
        return_value=MagicMock(messages=[], compacted_messages=None, estimated_tokens=0)
    )
    kernel._orchestrator = MagicMock()
    kernel._orchestrator.run = AsyncMock(
        return_value=MagicMock(final_content="HEARTBEAT_OK", tools_used=[], recovery_actions=[], messages=[])
    )
    kernel.hooks = MagicMock(
        run_session_start=AsyncMock(),
        run_session_end=AsyncMock(),
        run_message_sending=AsyncMock(return_value=MagicMock(cancel=False, content=None)),
    )
    kernel.engine = MagicMock(after_turn=AsyncMock())
    kernel.memory_lifecycle = None
    kernel.model = "model"
    kernel.temperature = 0.0
    kernel.max_tokens = 1000

    result = await RuntimeKernel._process_message(
        kernel,
        session_key="webui:chat-1",
        channel="webui",
        sender_id="system",
        chat_id="chat-1",
        content="heartbeat",
        metadata={"command_mode": "heartbeat", "is_meta_event": True},
    )

    assert result is None


@pytest.mark.asyncio
async def test_first_prompt_generates_ai_session_title() -> None:
    kernel = object.__new__(RuntimeKernel)
    kernel._set_tool_context = MagicMock()
    kernel._extract_attachments_legacy = AsyncMock(return_value=None)
    kernel._sanitize_assistant_output = RuntimeKernel._sanitize_assistant_output
    kernel.provider = MagicMock()
    kernel.provider.chat = AsyncMock(
        side_effect=[
            LLMResponse(content="如何写好公众号", tool_calls=[], usage={}),
        ]
    )
    kernel.sessions = MagicMock()
    session = MagicMock()
    session.key = "webui:chat-1"
    session.messages = []
    session.metadata = {}
    session.get_history.return_value = []
    kernel.sessions.get_or_create.return_value = session
    kernel._resolve_runtime_tools = MagicMock(return_value=MagicMock(tool_names=[]))
    kernel.assembler = MagicMock()
    kernel.assembler.assemble = AsyncMock(
        return_value=MagicMock(messages=[], compacted_messages=None, estimated_tokens=0)
    )
    kernel._orchestrator = MagicMock()
    kernel._orchestrator.run = AsyncMock(
        return_value=MagicMock(final_content="可以这样写。", tools_used=[], recovery_actions=[], messages=[])
    )
    kernel.memory_lifecycle = None
    kernel.model = "model"
    kernel.temperature = 0.0
    kernel.max_tokens = 1000

    await RuntimeKernel._process_message(
        kernel,
        session_key="webui:chat-1",
        channel="webui",
        sender_id="user",
        chat_id="webui:chat-1",
        content="你认为如何写好一篇微信公众号内容？",
        metadata={"command_mode": "prompt"},
    )

    assert session.metadata["title"] == "如何写好公众号"
    kernel.provider.chat.assert_awaited_once()
