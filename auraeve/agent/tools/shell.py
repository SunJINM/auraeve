from __future__ import annotations

import os
from typing import Any

from auraeve.agent.tools.base import Tool, ToolExecutionResult
from auraeve.agent_runtime.tool_runtime_context import get_current_tool_runtime_context
from auraeve.execution.dispatcher import ExecutionDispatcher
from auraeve.execution.host_ops import DEFAULT_DENY_PATTERNS, ShellCommandResult


class BashTool(Tool):
    """Execute Bash shell commands with Claude-style schema."""

    def __init__(
        self,
        timeout_ms: int = 60_000,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
        dispatcher: ExecutionDispatcher | None = None,
    ) -> None:
        self.timeout_ms = timeout_ms
        self.working_dir = working_dir
        self.deny_patterns = deny_patterns or list(DEFAULT_DENY_PATTERNS)
        self.restrict_to_workspace = restrict_to_workspace
        self._dispatcher = dispatcher or ExecutionDispatcher()

    @property
    def name(self) -> str:
        return "Bash"

    @property
    def description(self) -> str:
        return (
            "Use this tool to execute shell commands and return their output.\n\n"
            "Use it proactively when command execution will improve task quality, expand evidence, or validate behavior.\n"
            "- Read files: Read often gives more structured context, but Bash is also valid when shell inspection is the most effective path.\n"
            "- Edit files: Edit is precise for patching; Bash is useful for command-driven workflows.\n"
            "- Write files: Write is good for full-file output; Bash can still be used for build, test, git, package, and system tasks.\n"
            "- Content search: Grep is optimized for targeted search; Bash remains useful when search needs to be combined with other shell operations.\n"
            "- File search: Glob is optimized for file patterns; Bash is still valid for broader shell-driven investigation.\n"
            "- Communication: output text directly\n"
            "- If the commands are independent and can run in parallel, make multiple Bash tool calls in a single message.\n"
            "- If the commands depend on each other and must run sequentially, use a single Bash call with '&&' to chain them together."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Bash command to execute"},
                "timeout": {
                    "type": "integer",
                    "description": "Optional timeout in milliseconds.",
                    "minimum": 1,
                },
                "description": {
                    "type": "string",
                    "description": "Short explanation of the command purpose.",
                },
                "run_in_background": {
                    "type": "boolean",
                    "description": "Whether to run the command in the background.",
                },
                "dangerouslyDisableSandbox": {
                    "type": "boolean",
                    "description": "Disable sandbox protections for this command.",
                },
            },
            "required": ["command"],
        }

    async def execute(
        self,
        command: str,
        timeout: int | None = None,
        description: str | None = None,
        run_in_background: bool = False,
        dangerouslyDisableSandbox: bool = False,
        **kwargs: Any,
    ) -> ToolExecutionResult:
        del description, kwargs
        runtime_ctx = get_current_tool_runtime_context()
        cwd = getattr(runtime_ctx, "shell_cwd", None) or self.working_dir or os.getcwd()
        try:
            result = await self._dispatcher.exec_command(
                command=command,
                working_dir=cwd,
                timeout_ms=timeout if timeout is not None else self.timeout_ms,
                deny_patterns=self.deny_patterns,
                restrict_to_workspace=self.restrict_to_workspace,
                run_in_background=run_in_background,
                dangerously_disable_sandbox=dangerouslyDisableSandbox,
            )
        except Exception as exc:
            return ToolExecutionResult(content=f"Command failed: {exc}")

        if runtime_ctx is not None and result.cwd:
            runtime_ctx.shell_cwd = result.cwd

        return ToolExecutionResult(
            content=self._format_result(result),
            data=result.to_payload(),
        )

    @staticmethod
    def _format_result(result: ShellCommandResult) -> str:
        if result.backgroundTaskId:
            return (
                "Command is running in the background.\n"
                f"backgroundTaskId: {result.backgroundTaskId}\n"
                f"outputFilePath: {result.outputFilePath or ''}"
            ).strip()
        parts: list[str] = []
        if result.stdout:
            parts.append(result.stdout)
        if result.stderr:
            parts.append(f"STDERR:\n{result.stderr}")
        if result.code != 0:
            parts.append(f"\nExitCode: {result.code}")
        if not parts:
            parts.append("(no output)")
        return "\n".join(parts)
