from unittest.mock import AsyncMock, MagicMock

import pytest

from auraeve.agent_runtime.command_types import QueuedCommand
from auraeve.agent_runtime.kernel import RuntimeKernel


@pytest.mark.asyncio
async def test_execute_command_projects_messages_and_delegates() -> None:
    kernel = object.__new__(RuntimeKernel)
    kernel._mcp_runtime = MagicMock()
    kernel._mcp_runtime.start = AsyncMock()
    kernel._process_projected_command = AsyncMock(return_value="ok")

    command = QueuedCommand(
        id="cmd-1",
        session_key="webui:chat-1",
        source="webui",
        mode="prompt",
        priority="next",
        payload={"content": "hello"},
        origin={"kind": "user"},
    )

    result = await RuntimeKernel.execute_command(kernel, command)

    assert result == "ok"
    kernel._mcp_runtime.start.assert_awaited_once()
    kernel._process_projected_command.assert_awaited_once()
    projected = kernel._process_projected_command.await_args.args[1]
    assert projected == [{"role": "user", "content": "hello"}]


@pytest.mark.asyncio
async def test_process_projected_command_passes_raw_command_fields() -> None:
    kernel = object.__new__(RuntimeKernel)
    kernel._process_message = AsyncMock(return_value="ok")

    command = QueuedCommand(
        id="cmd-2",
        session_key="webui:chat-2",
        source="webui",
        mode="prompt",
        priority="next",
        payload={
            "channel": "webui",
            "sender_id": "u-1",
            "chat_id": "chat-2",
            "media": ["img://1"],
            "attachments": ["att-1"],
            "metadata": {"trace_id": "t-1"},
        },
        origin={"kind": "user"},
    )

    result = await RuntimeKernel._process_projected_command(
        kernel,
        command,
        [{"role": "user", "content": "hello"}, {"role": "user", "content": "world"}],
    )

    assert result == "ok"
    kernel._process_message.assert_awaited_once_with(
        session_key="webui:chat-2",
        channel="webui",
        sender_id="u-1",
        chat_id="chat-2",
        content="hello\n\nworld",
        media=["img://1"],
        attachments=["att-1"],
        metadata={"trace_id": "t-1", "command_mode": "prompt", "command_origin": {"kind": "user"}},
    )


def test_kernel_has_no_process_direct() -> None:
    assert not hasattr(RuntimeKernel, "process_direct")


def test_no_publish_inbound_call_sites_left() -> None:
    import subprocess

    result = subprocess.run(
        ["rg", "-n", "publish_inbound\\(|consume_inbound\\(", "auraeve", "main.py"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1


def test_kernel_no_longer_rewraps_commands_as_inbound_messages() -> None:
    import subprocess

    result = subprocess.run(
        ["rg", "-n", "InboundMessage", "auraeve/agent_runtime/kernel.py"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1


@pytest.mark.asyncio
async def test_process_message_no_longer_builds_identity_context() -> None:
    kernel = object.__new__(RuntimeKernel)
    kernel._media_runtime = None
    kernel._plan = MagicMock()
    kernel._plan.clear_plan = MagicMock()
    kernel._plan.format_for_prompt = MagicMock(return_value="")
    kernel._set_tool_context = MagicMock()
    kernel._set_media_understand_context = MagicMock()
    kernel._extract_attachments_legacy = AsyncMock(return_value=None)
    kernel._inject_plan_into_messages = MagicMock(side_effect=lambda messages, _: messages)
    kernel._sanitize_assistant_output = RuntimeKernel._sanitize_assistant_output
    kernel.sessions = MagicMock()
    session = MagicMock()
    session.key = "webui:chat-1"
    session.get_history.return_value = []
    kernel.sessions.get_or_create.return_value = session
    kernel.assembler = MagicMock()
    kernel.assembler.assemble = AsyncMock(
        return_value=MagicMock(messages=[], compacted_messages=None, estimated_tokens=0)
    )
    kernel._orchestrator = MagicMock()
    kernel._orchestrator.run = AsyncMock(
        return_value=MagicMock(final_content="ok", tools_used=[], recovery_actions=[])
    )
    kernel.hooks = MagicMock(
        run_session_start=AsyncMock(),
        run_session_end=AsyncMock(),
        run_message_sending=AsyncMock(return_value=MagicMock(cancel=False, content="ok")),
    )
    kernel.engine = MagicMock(after_turn=AsyncMock())
    kernel.memory_lifecycle = None
    kernel.tools = MagicMock(tool_names=[])
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

    assemble_kwargs = kernel.assembler.assemble.await_args.kwargs
    assert "identity_context" not in assemble_kwargs
