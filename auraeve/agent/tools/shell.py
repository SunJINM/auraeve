from __future__ import annotations

import os
from typing import Any

from auraeve.agent.tools.base import Tool
from auraeve.execution.dispatcher import ExecutionDispatcher
from auraeve.execution.host_ops import DEFAULT_DENY_PATTERNS


class ExecTool(Tool):
    """Execute shell command and return output."""

    def __init__(
        self,
        timeout: int = 60,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
        dispatcher: ExecutionDispatcher | None = None,
    ) -> None:
        self.timeout = timeout
        self.working_dir = working_dir
        self.deny_patterns = deny_patterns or list(DEFAULT_DENY_PATTERNS)
        self.restrict_to_workspace = restrict_to_workspace
        self._dispatcher = dispatcher or ExecutionDispatcher()

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return "Execute shell command and return output."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command"},
                "working_dir": {"type": "string", "description": "Optional working directory"},
            },
            "required": ["command"],
        }

    async def execute(self, command: str, working_dir: str | None = None, **kwargs: Any) -> str:
        cwd = working_dir or self.working_dir or os.getcwd()
        try:
            return await self._dispatcher.exec_command(
                command=command,
                working_dir=cwd,
                timeout=self.timeout,
                deny_patterns=self.deny_patterns,
                restrict_to_workspace=self.restrict_to_workspace,
            )
        except Exception as exc:
            return f"Command failed: {exc}"
