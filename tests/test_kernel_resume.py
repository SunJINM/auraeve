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
