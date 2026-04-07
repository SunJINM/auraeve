from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .host_ops import (
    DEFAULT_DENY_PATTERNS,
    execute_shell_command,
    read_file,
    write_file,
)


class ExecutionBackend(Protocol):
    async def exec_command(
        self,
        *,
        command: str,
        working_dir: str | None,
        timeout: int,
        deny_patterns: list[str] | None,
        restrict_to_workspace: bool,
    ) -> str: ...

    async def read_file(
        self,
        *,
        path: str,
        allowed_dir: str | None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> str: ...
    async def write_file(
        self,
        *,
        path: str,
        content: str,
        allowed_dir: str | None,
    ) -> tuple[str, str | None]: ...

@dataclass(slots=True)
class LocalExecutionBackend:
    async def exec_command(
        self,
        *,
        command: str,
        working_dir: str | None,
        timeout: int,
        deny_patterns: list[str] | None,
        restrict_to_workspace: bool,
    ) -> str:
        return await execute_shell_command(
            command=command,
            timeout=timeout,
            working_dir=working_dir,
            deny_patterns=deny_patterns,
            restrict_to_workspace=restrict_to_workspace,
        )

    async def read_file(
        self,
        *,
        path: str,
        allowed_dir: str | None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> str:
        allowed = Path(allowed_dir).expanduser().resolve() if allowed_dir else None
        return read_file(path=path, allowed_dir=allowed, offset=offset, limit=limit)

    async def write_file(
        self,
        *,
        path: str,
        content: str,
        allowed_dir: str | None,
    ) -> tuple[str, str | None]:
        allowed = Path(allowed_dir).expanduser().resolve() if allowed_dir else None
        return write_file(path=path, content=content, allowed_dir=allowed)


class ExecutionDispatcher:
    """Unified execution router. Default backend is local host execution."""

    def __init__(self, backend: ExecutionBackend | None = None) -> None:
        self._backend = backend or LocalExecutionBackend()

    async def exec_command(
        self,
        *,
        command: str,
        working_dir: str | None,
        timeout: int,
        deny_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
    ) -> str:
        return await self._backend.exec_command(
            command=command,
            working_dir=working_dir,
            timeout=timeout,
            deny_patterns=deny_patterns or list(DEFAULT_DENY_PATTERNS),
            restrict_to_workspace=restrict_to_workspace,
        )

    async def read_file(
        self,
        *,
        path: str,
        allowed_dir: str | None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> str:
        return await self._backend.read_file(
            path=path,
            allowed_dir=allowed_dir,
            offset=offset,
            limit=limit,
        )

    async def write_file(
        self,
        *,
        path: str,
        content: str,
        allowed_dir: str | None,
    ) -> tuple[str, str | None]:
        return await self._backend.write_file(path=path, content=content, allowed_dir=allowed_dir)
