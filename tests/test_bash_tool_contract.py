from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from auraeve.agent.tools.base import ToolExecutionResult
from auraeve.agent.tools.shell import BashTool
from auraeve.agent_runtime.tool_runtime_context import (
    FileReadStateStore,
    TaskReadStateStore,
    ToolRuntimeContext,
    use_tool_runtime_context,
)
from auraeve.execution.host_ops import ShellCommandResult


def test_bash_tool_exposes_claude_style_name_and_parameters() -> None:
    tool = BashTool()

    assert tool.name == "Bash"
    assert tool.parameters["required"] == ["command"]

    props = tool.parameters["properties"]
    assert set(props) >= {
        "command",
        "timeout",
        "description",
        "run_in_background",
        "dangerouslyDisableSandbox",
    }
    assert props["timeout"]["type"] == "integer"
    assert props["run_in_background"]["type"] == "boolean"
    assert props["dangerouslyDisableSandbox"]["type"] == "boolean"


@pytest.mark.asyncio
async def test_bash_tool_returns_structured_result_and_tracks_shell_cwd(tmp_path) -> None:
    initial_cwd = str(tmp_path)
    next_cwd = str(tmp_path / "subdir")
    dispatcher = AsyncMock()
    dispatcher.exec_command = AsyncMock(
        side_effect=[
            ShellCommandResult(
                stdout="first",
                stderr="",
                code=0,
                interrupted=False,
                cwd=next_cwd,
            ),
            ShellCommandResult(
                stdout="second",
                stderr="",
                code=0,
                interrupted=False,
                cwd=next_cwd,
            ),
        ]
    )
    tool = BashTool(working_dir=initial_cwd, dispatcher=dispatcher)
    ctx = ToolRuntimeContext(
        file_reads=FileReadStateStore(),
        task_reads=TaskReadStateStore(),
    )

    with use_tool_runtime_context(ctx):
        first = await tool.execute(command="pwd")
        second = await tool.execute(command="pwd")

    assert isinstance(first, ToolExecutionResult)
    assert first.data["stdout"] == "first"
    assert first.data["code"] == 0
    assert isinstance(second, ToolExecutionResult)
    assert second.data["stdout"] == "second"

    first_call = dispatcher.exec_command.await_args_list[0].kwargs
    second_call = dispatcher.exec_command.await_args_list[1].kwargs
    assert first_call["working_dir"] == initial_cwd
    assert second_call["working_dir"] == next_cwd


@pytest.mark.asyncio
async def test_bash_tool_passes_background_and_timeout_options(tmp_path) -> None:
    dispatcher = AsyncMock()
    dispatcher.exec_command = AsyncMock(
        return_value=ShellCommandResult(
            stdout="",
            stderr="",
            code=0,
            interrupted=False,
            backgroundTaskId="bg-1",
            backgroundedByUser=True,
            cwd=str(tmp_path),
        )
    )
    tool = BashTool(working_dir=str(tmp_path), dispatcher=dispatcher)

    result = await tool.execute(
        command="sleep 10",
        timeout=12_345,
        run_in_background=True,
        description="wait",
        dangerouslyDisableSandbox=True,
    )

    assert isinstance(result, ToolExecutionResult)
    assert result.data["backgroundTaskId"] == "bg-1"
    call_kwargs = dispatcher.exec_command.await_args.kwargs
    assert call_kwargs["timeout_ms"] == 12_345
    assert call_kwargs["run_in_background"] is True
    assert call_kwargs["dangerously_disable_sandbox"] is True
