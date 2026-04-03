from __future__ import annotations

import difflib
import re
import time
from pathlib import Path
from typing import Any

from auraeve.agent.tools import file_read_support
from auraeve.agent.tools.base import Tool, ToolExecutionResult
from auraeve.agent_runtime.tool_runtime_context import (
    FileReadSnapshot,
    get_current_tool_runtime_context,
)
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

    def _resolve_path(self, file_path: str) -> Path:
        resolved = Path(file_path).expanduser().resolve()
        if self._allowed_dir is not None:
            allowed_root = self._allowed_dir.expanduser().resolve()
            if allowed_root != resolved and allowed_root not in resolved.parents:
                raise PermissionError(f"path {file_path} escapes allowed dir {allowed_root}")
        return resolved


class ReadTool(_FsToolBase):
    @property
    def name(self) -> str:
        return "Read"

    @property
    def description(self) -> str:
        return "Read a file from the local filesystem."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the file"},
                "offset": {"type": "integer", "description": "Optional zero-based line offset"},
                "limit": {"type": "integer", "description": "Optional number of lines to read"},
                "pages": {"type": "string", "description": "Optional PDF page range"},
            },
            "required": ["file_path"],
        }

    async def execute(
        self,
        file_path: str,
        offset: int | None = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> ToolExecutionResult:
        try:
            if not Path(file_path).is_absolute():
                return ToolExecutionResult(content="Error: file_path must be absolute")

            resolved = self._resolve_path(file_path)
            if not resolved.exists():
                return ToolExecutionResult(content=f"Error: file not found: {resolved}")
            if not resolved.is_file():
                return ToolExecutionResult(content=f"Error: not a file: {resolved}")

            pages = kwargs.get("pages")
            ctx = get_current_tool_runtime_context()
            current_mtime_ms = int(resolved.stat().st_mtime * 1000)
            existing_snapshot = ctx.file_reads.get(str(resolved)) if ctx is not None else None
            if (
                existing_snapshot is not None
                and existing_snapshot.file_mtime_ms == current_mtime_ms
                and not existing_snapshot.is_partial_view
                and offset is None
                and limit is None
                and not pages
            ):
                return ToolExecutionResult(
                    content=file_read_support.FILE_UNCHANGED_STUB,
                    data={"type": "file_unchanged", "filePath": str(resolved)},
                )

            suffix = resolved.suffix.lower()
            content_type = "text"
            raw_text_for_state: str | None = None
            if suffix in file_read_support.IMAGE_SUFFIXES:
                result = await file_read_support.read_image_file(str(resolved))
                content_type = "image"
            elif suffix == ".pdf":
                result = await file_read_support.read_pdf_file(str(resolved), pages)
                content_type = "pdf"
            elif suffix == ".ipynb":
                result = file_read_support.read_notebook_file(str(resolved))
                content_type = "notebook"
                raw_text_for_state = resolved.read_text(encoding="utf-8")
            else:
                raw_text_for_state = resolved.read_text(encoding="utf-8")
                rendered = file_read_support.format_text_with_line_numbers(
                    raw_text_for_state,
                    offset,
                    limit,
                )
                result = ToolExecutionResult(
                    content=rendered,
                    data={
                        "type": "text",
                        "filePath": str(resolved),
                        "offset": offset,
                        "limit": limit,
                    },
                )

            if ctx is not None and not str(result.content).startswith("Error:"):
                ctx.file_reads.record(
                    FileReadSnapshot(
                        file_path=str(resolved),
                        timestamp_ms=int(time.time() * 1000),
                        file_mtime_ms=current_mtime_ms,
                        is_partial_view=offset is not None or limit is not None or bool(pages),
                        content_type=content_type,
                        content=raw_text_for_state,
                        offset=offset,
                        limit=limit,
                        pages=pages,
                    )
                )

            return result
        except PermissionError as exc:
            return ToolExecutionResult(content=f"Error: {exc}")
        except Exception as exc:
            return ToolExecutionResult(content=f"Read failed: {exc}")


class WriteTool(_FsToolBase):
    @property
    def name(self) -> str:
        return "Write"

    @property
    def description(self) -> str:
        return "Write a file to the local filesystem."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the file"},
                "content": {"type": "string", "description": "Full file contents"},
            },
            "required": ["file_path", "content"],
        }

    async def execute(self, file_path: str, content: str, **kwargs: Any) -> ToolExecutionResult:
        try:
            if not Path(file_path).is_absolute():
                return ToolExecutionResult(content="Error: file_path must be absolute")

            resolved = self._resolve_path(file_path)
            ctx = get_current_tool_runtime_context()
            original: str | None = None

            if resolved.exists():
                snapshot = ctx.file_reads.get(str(resolved)) if ctx is not None else None
                if snapshot is None:
                    return ToolExecutionResult(
                        content="Error: existing files must be read with Read before Write"
                    )
                if snapshot.is_partial_view:
                    return ToolExecutionResult(
                        content="Error: file was only partially read; read the whole file before Write"
                    )
                current_mtime_ms = int(resolved.stat().st_mtime * 1000)
                if current_mtime_ms > snapshot.file_mtime_ms:
                    current_content = resolved.read_text(encoding="utf-8")
                    if snapshot.content != current_content:
                        return ToolExecutionResult(
                            content="Error: file changed after Read; read it again before Write"
                        )
                original = resolved.read_text(encoding="utf-8")

            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")

            data = {
                "type": "create" if original is None else "update",
                "filePath": str(resolved),
                "content": content,
                "structuredPatch": _build_structured_patch(original or "", content)
                if original is not None
                else [],
                "originalFile": original,
            }

            if ctx is not None:
                ctx.file_reads.record(
                    FileReadSnapshot(
                        file_path=str(resolved),
                        timestamp_ms=int(time.time() * 1000),
                        file_mtime_ms=int(resolved.stat().st_mtime * 1000),
                        is_partial_view=False,
                        content_type="text",
                        content=content,
                        offset=None,
                        limit=None,
                        pages=None,
                    )
                )

            if original is None:
                return ToolExecutionResult(
                    content=f"File created successfully at: {resolved}",
                    data=data,
                )
            return ToolExecutionResult(
                content=f"The file {resolved} has been updated successfully.",
                data=data,
            )
        except PermissionError as exc:
            return ToolExecutionResult(content=f"Error: {exc}")
        except Exception as exc:
            return ToolExecutionResult(content=f"Write failed: {exc}")


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


ReadFileTool = ReadTool
WriteFileTool = WriteTool

_HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_lines>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_lines>\d+))? @@"
)


def _build_structured_patch(old_content: str, new_content: str) -> list[dict[str, Any]]:
    diff_lines = list(
        difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            lineterm="",
            n=3,
        )
    )
    hunks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in diff_lines:
        if line.startswith("--- ") or line.startswith("+++ "):
            continue
        if line.startswith("@@"):
            if current is not None:
                hunks.append(current)
            match = _HUNK_RE.match(line)
            if not match:
                continue
            current = {
                "oldStart": int(match.group("old_start")),
                "oldLines": int(match.group("old_lines") or "1"),
                "newStart": int(match.group("new_start")),
                "newLines": int(match.group("new_lines") or "1"),
                "lines": [],
            }
            continue
        if current is not None:
            current["lines"].append(line)
    if current is not None:
        hunks.append(current)
    return hunks
