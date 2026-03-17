"""执行沙箱：根据风险等级选择执行模式。"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class ExecutionConstraints:
    timeout_s: int = 60
    max_memory_mb: int = 512
    allowed_paths: list[str] = field(default_factory=list)
    denied_commands: list[str] = field(default_factory=lambda: [
        "rm -rf /", "format", "shutdown", "reboot",
        "dd if=", "mkfs", "> /dev/sda",
    ])


class SandboxExecutor:
    """分层执行沙箱。"""

    def __init__(
        self,
        constraints: ExecutionConstraints | None = None,
        docker_enabled: bool = False,
    ) -> None:
        self._constraints = constraints or ExecutionConstraints()
        self._docker_enabled = docker_enabled and shutil.which("docker") is not None

    def is_command_denied(self, cmd: str) -> bool:
        cmd_lower = cmd.lower().strip()
        return any(d in cmd_lower for d in self._constraints.denied_commands)

    async def execute_command(
        self,
        cmd: str,
        working_dir: str | None = None,
        risk_level: str = "low",
    ) -> dict[str, Any]:
        if self.is_command_denied(cmd):
            return {"ok": False, "output": "", "error": f"命令被拒绝: {cmd}"}

        if risk_level == "critical" and self._docker_enabled:
            return await self._exec_docker(cmd, working_dir)

        return await self._exec_subprocess(cmd, working_dir)

    async def _exec_subprocess(
        self, cmd: str, working_dir: str | None = None
    ) -> dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._constraints.timeout_s,
            )
            output = stdout.decode("utf-8", errors="replace")
            err = stderr.decode("utf-8", errors="replace")
            return {
                "ok": proc.returncode == 0,
                "output": output[:8000],
                "error": err[:2000] if err else "",
            }
        except asyncio.TimeoutError:
            return {"ok": False, "output": "", "error": f"执行超时（{self._constraints.timeout_s}s）"}
        except Exception as e:
            return {"ok": False, "output": "", "error": str(e)}

    async def _exec_docker(
        self, cmd: str, working_dir: str | None = None
    ) -> dict[str, Any]:
        mount = f"-v {working_dir}:/workspace -w /workspace" if working_dir else ""
        docker_cmd = f'docker run --rm --network none {mount} python:3.11-slim sh -c "{cmd}"'
        return await self._exec_subprocess(docker_cmd)
