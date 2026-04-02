import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
import pytest
from auraeve.agent_runtime.kernel import RuntimeKernel


def _make_kernel():
    kernel = object.__new__(RuntimeKernel)
    kernel.sessions = MagicMock()
    kernel.assembler = MagicMock()
    kernel._orchestrator = MagicMock()
    kernel.tools = MagicMock()
    kernel.tools.tool_names = []
    kernel.model = "claude-sonnet-4-6"
    kernel.temperature = 0.7
    kernel.max_tokens = 4096
    kernel.engine = MagicMock()
    kernel._bus = MagicMock()
    kernel._set_tool_context = MagicMock()
    return kernel


@pytest.mark.asyncio
async def test_resume_with_subagent_result_sends_outbound():
    kernel = _make_kernel()

    session = MagicMock()
    session.get_history.return_value = [
        {"role": "user", "content": "帮我分析"},
        {"role": "assistant", "content": "已派出子体"},
    ]
    kernel.sessions.get_or_create.return_value = session

    assemble_result = MagicMock()
    assemble_result.messages = session.get_history.return_value + [
        {"role": "assistant", "content": None, "tool_calls": [{"id": "call_x", "type": "function", "function": {"name": "subagent_result", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_x", "name": "subagent_result", "content": "{}"},
    ]
    assemble_result.compacted_messages = None
    kernel.assembler.assemble = AsyncMock(return_value=assemble_result)

    run_result = MagicMock()
    run_result.final_content = "分析完成，结果如下..."
    run_result.tools_used = []
    run_result.recovery_actions = []
    kernel._orchestrator.run = AsyncMock(return_value=run_result)
    kernel.engine.after_turn = AsyncMock()

    outbound = await kernel._resume_with_subagent_result(
        session_key="webui:chat1",
        channel="webui",
        chat_id="chat1",
        synthetic_messages=[
            {"role": "assistant", "content": None, "tool_calls": [{"id": "call_x", "type": "function", "function": {"name": "subagent_result", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "call_x", "name": "subagent_result", "content": "{}"},
        ],
        runtime_instruction="若已告知用户处理中，直接给出结果。",
    )

    assert outbound is not None
    assert outbound.channel == "webui"
    assert outbound.chat_id == "chat1"
    assert "分析完成" in outbound.content
    session.add_message.assert_called()
    kernel.sessions.save.assert_called_once_with(session)


@pytest.mark.asyncio
async def test_resume_with_compacted_messages_calls_replace_history():
    kernel = _make_kernel()

    session = MagicMock()
    session.get_history.return_value = [{"role": "user", "content": "hello"}]
    kernel.sessions.get_or_create.return_value = session

    compacted = [{"role": "user", "content": "compacted"}]
    assemble_result = MagicMock()
    assemble_result.messages = compacted
    assemble_result.compacted_messages = compacted  # 触发 replace_history 分支
    kernel.assembler.assemble = AsyncMock(return_value=assemble_result)

    run_result = MagicMock()
    run_result.final_content = "ok"
    kernel._orchestrator.run = AsyncMock(return_value=run_result)
    kernel.engine.after_turn = AsyncMock()

    await kernel._resume_with_subagent_result(
        session_key="webui:chat1",
        channel="webui",
        chat_id="chat1",
        synthetic_messages=[],
    )

    session.replace_history.assert_called_once_with(compacted)


@pytest.mark.asyncio
async def test_resume_without_session_key_falls_back_to_channel_and_chat_id():
    kernel = _make_kernel()

    session = MagicMock()
    session.get_history.return_value = [{"role": "user", "content": "hello"}]
    kernel.sessions.get_or_create.return_value = session

    assemble_result = MagicMock()
    assemble_result.messages = session.get_history.return_value
    assemble_result.compacted_messages = None
    kernel.assembler.assemble = AsyncMock(return_value=assemble_result)

    run_result = MagicMock()
    run_result.final_content = "ok"
    kernel._orchestrator.run = AsyncMock(return_value=run_result)
    kernel.engine.after_turn = AsyncMock()

    await kernel._resume_with_subagent_result(
        channel="webui",
        chat_id="chat1",
        synthetic_messages=[],
    )

    kernel.sessions.get_or_create.assert_called_once_with("webui:chat1")
