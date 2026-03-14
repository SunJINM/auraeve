from __future__ import annotations

from pathlib import Path
from typing import Any

from auraeve.agent.tools.base import Tool
from auraeve.execution.dispatcher import ExecutionDispatcher


class _FsToolBase(Tool):
    def __init__(
        self,
        allowed_dir: Path | None = None,
        dispatcher: ExecutionDispatcher | None = None,
    ) -> None:
        self._allowed_dir = allowed_dir
        self._dispatcher = dispatcher or ExecutionDispatcher()

    @property
    def _allowed_dir_str(self) -> str | None:
        if self._allowed_dir is None:
            return None
        return str(self._allowed_dir)


class ReadFileTool(_FsToolBase):
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read file contents"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path"}},
            "required": ["path"],
        }

    async def execute(self, path: str, **kwargs: Any) -> str:
        try:
            return await self._dispatcher.read_file(path=path, allowed_dir=self._allowed_dir_str)
        except PermissionError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            return f"Read failed: {exc}"


class WriteFileTool(_FsToolBase):
    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to file"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Target file path"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        try:
            return await self._dispatcher.write_file(
                path=path,
                content=content,
                allowed_dir=self._allowed_dir_str,
            )
        except PermissionError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            return f"Write failed: {exc}"


class EditFileTool(_FsToolBase):
    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return "Replace old_text with new_text in file"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "old_text": {"type": "string", "description": "Exact old text"},
                "new_text": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_text", "new_text"],
        }

    async def execute(self, path: str, old_text: str, new_text: str, **kwargs: Any) -> str:
        try:
            return await self._dispatcher.edit_file(
                path=path,
                old_text=old_text,
                new_text=new_text,
                allowed_dir=self._allowed_dir_str,
            )
        except PermissionError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            return f"Edit failed: {exc}"


class ListDirTool(_FsToolBase):
    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return "List directory entries"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Directory path"}},
            "required": ["path"],
        }

    async def execute(self, path: str, **kwargs: Any) -> str:
        try:
            return await self._dispatcher.list_dir(path=path, allowed_dir=self._allowed_dir_str)
        except PermissionError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            return f"List failed: {exc}"
