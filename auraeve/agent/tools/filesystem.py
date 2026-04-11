from __future__ import annotations

import difflib
import re
import time
from pathlib import Path
from typing import Any

import auraeve.config as cfg
from auraeve.agent.tools import file_read_support
from auraeve.agent.tools import file_edit_support
from auraeve.agent.tools.image_to_text_service import ImageToTextService
from auraeve.agent.tools.read_router import ReadRouter
from auraeve.agent.tools.base import Tool, ToolExecutionResult
from auraeve.agent_runtime.tool_runtime_context import (
    FileReadSnapshot,
    get_current_tool_runtime_context,
)
from auraeve.execution.dispatcher import ExecutionDispatcher
from auraeve.llm.model_registry import ModelRegistry
from auraeve.stt.runtime import build_runtime_from_config


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
        return (
            "Reads a file from the local filesystem.\n\n"
            "Usage:\n"
            "- The file_path parameter must be an absolute path, not a relative path.\n"
            "- By default, it reads the whole file when it fits within the text token budget.\n"
            "- If the file is too large, use offset and limit or search for specific content instead.\n"
            "- start with a full read when broad context will improve quality or when you may need to edit the file later.\n"
            "- Use targeted partial reads with offset and limit when you already know the relevant region.\n"
            "- This tool can read images.\n"
            "- This tool can read audio files and return a transcription when ASR is configured.\n"
            "- This tool can read PDF files.\n"
            "- This tool can read Jupyter notebooks.\n"
            "- This tool can only read files, not directories."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the file"},
                "offset": {"type": "integer", "description": "Optional zero-based line offset. Omit for a full read."},
                "limit": {"type": "integer", "description": "Optional number of lines to read. Omit for a full read."},
                "pages": {"type": "string", "description": "Optional PDF page range. Omit for a full read."},
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
            normalized_pages = str(pages).strip() if pages is not None else None
            if normalized_pages == "":
                normalized_pages = None
            normalized_offset, normalized_limit = _normalize_default_text_read_args(
                offset,
                limit,
            )
            ctx = get_current_tool_runtime_context()
            current_mtime_ms = int(resolved.stat().st_mtime * 1000)
            existing_snapshot = ctx.file_reads.get(str(resolved)) if ctx is not None else None
            if (
                existing_snapshot is not None
                and existing_snapshot.file_mtime_ms == current_mtime_ms
                and not existing_snapshot.is_partial_view
                and normalized_offset is None
                and normalized_limit is None
                and not normalized_pages
            ):
                return ToolExecutionResult(
                    content=file_read_support.FILE_UNCHANGED_STUB,
                    data={"type": "file_unchanged", "filePath": str(resolved)},
                )

            suffix = resolved.suffix.lower()
            content_type = "text"
            raw_text_for_state: str | None = None
            encoding: str | None = None
            line_endings: str | None = None
            if suffix == ".ipynb":
                result = file_read_support.read_notebook_file(str(resolved))
                content_type = "notebook"
                notebook_meta = file_edit_support.read_text_file_with_metadata(str(resolved))
                raw_text_for_state = notebook_meta.content
                encoding = notebook_meta.encoding
                line_endings = notebook_meta.line_endings
            else:
                if suffix not in file_read_support.IMAGE_SUFFIXES and suffix not in file_read_support.AUDIO_SUFFIXES and suffix != ".pdf":
                    text_meta = file_edit_support.read_text_file_with_metadata(str(resolved))
                    raw_text_for_state = text_meta.content
                    encoding = text_meta.encoding
                    line_endings = text_meta.line_endings

                config = cfg.export_config(mask_sensitive=False)
                router = ReadRouter(
                    model_registry=ModelRegistry(list(config.get("LLM_MODELS") or [])),
                    image_to_text_service=ImageToTextService(
                        prompt=str((config.get("READ_ROUTING") or {}).get("imageToTextPrompt") or "")
                    ),
                    asr_runtime=build_runtime_from_config(config),
                    read_routing=dict(config.get("READ_ROUTING") or {}),
                )
                result = await router.read_file(
                    str(resolved),
                    offset=normalized_offset,
                    limit=normalized_limit,
                    pages=normalized_pages,
                )
                content_type = str((result.data or {}).get("type") or "text")

            if ctx is not None and not str(result.content).startswith("Error:"):
                is_partial_view = _is_partial_read_view(
                    content=raw_text_for_state,
                    content_type=content_type,
                    offset=normalized_offset,
                    limit=normalized_limit,
                    pages=normalized_pages,
                )
                ctx.file_reads.record(
                    FileReadSnapshot(
                        file_path=str(resolved),
                        timestamp_ms=int(time.time() * 1000),
                        file_mtime_ms=current_mtime_ms,
                        is_partial_view=is_partial_view,
                        content_type=content_type,
                        content=raw_text_for_state,
                        offset=normalized_offset,
                        limit=normalized_limit,
                        pages=normalized_pages,
                        encoding=encoding,
                        line_endings=line_endings,
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
            encoding = "utf-8"
            line_endings = "LF"

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
                original_meta = file_edit_support.read_text_file_with_metadata(str(resolved))
                if snapshot.content != original_meta.content:
                    return ToolExecutionResult(
                        content="Error: file changed after Read; read it again before Write"
                    )
                original = original_meta.content
                encoding = original_meta.encoding
                line_endings = original_meta.line_endings

            resolved.parent.mkdir(parents=True, exist_ok=True)
            file_edit_support.write_text_with_metadata(
                str(resolved),
                content,
                encoding=encoding,
                line_endings=line_endings,
            )

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
                        encoding=encoding,
                        line_endings=line_endings,
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


class EditTool(_FsToolBase):
    @property
    def name(self) -> str:
        return "Edit"

    @property
    def description(self) -> str:
        return "Performs exact string replacements in files."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the file"},
                "old_string": {"type": "string", "description": "The text to replace"},
                "new_string": {
                    "type": "string",
                    "description": "The text to replace it with (must be different from old_string)",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences of old_string (default false)",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        }

    async def execute(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        **kwargs: Any,
    ) -> ToolExecutionResult:
        try:
            if not Path(file_path).is_absolute():
                return ToolExecutionResult(content="Error: file_path must be absolute")

            resolved = self._resolve_path(file_path)

            if old_string == new_string:
                return ToolExecutionResult(
                    content="No changes to make: old_string and new_string are exactly the same."
                )

            text_meta = file_edit_support.read_text_file_with_metadata(str(resolved))
            normalized_old, normalized_new = file_edit_support.normalize_edit_strings(
                file_path=str(resolved),
                file_content=text_meta.content if text_meta.file_exists else None,
                old_string=old_string,
                new_string=new_string,
            )

            if not text_meta.file_exists:
                if normalized_old != "":
                    return ToolExecutionResult(
                        content=(
                            "File does not exist. Read it first or use old_string=\"\" "
                            "to create a new file with Edit."
                        )
                    )

                file_edit_support.write_text_with_metadata(
                    str(resolved),
                    normalized_new,
                    encoding=text_meta.encoding,
                    line_endings=text_meta.line_endings,
                )
                return self._build_edit_result(
                    resolved=resolved,
                    original_file="",
                    old_string="",
                    new_string=new_string,
                    updated_file=normalized_new,
                    replace_all=bool(replace_all),
                )

            if normalized_old == "" and text_meta.content.strip() != "":
                return ToolExecutionResult(content="Cannot create new file - file already exists.")

            if resolved.suffix.lower() == ".ipynb" and normalized_old != "":
                return ToolExecutionResult(
                    content="File is a Jupyter Notebook. Use the NotebookEdit tool to edit this file."
                )

            ctx = get_current_tool_runtime_context()
            snapshot = ctx.file_reads.get(str(resolved)) if ctx is not None else None
            if snapshot is None:
                return ToolExecutionResult(
                    content="File has not been read yet. Read it first before writing to it."
                )
            if snapshot.is_partial_view:
                return ToolExecutionResult(
                    content="File was only partially read. Read the whole file before editing."
                )

            if snapshot.content != text_meta.content:
                return ToolExecutionResult(
                    content=(
                        "File has been modified since Read, either by the user or by a linter. "
                        "Read it again before attempting to write it."
                    )
                )

            actual_old_string = file_edit_support.find_actual_string(text_meta.content, normalized_old)
            if actual_old_string is None:
                return ToolExecutionResult(
                    content=f"String to replace not found in file.\nString: {old_string}"
                )

            matches = text_meta.content.count(actual_old_string)
            if matches > 1 and not replace_all:
                return ToolExecutionResult(
                    content=(
                        f"Found {matches} matches of the string to replace, but replace_all is false. "
                        "To replace all occurrences, set replace_all to true. To replace only one occurrence, "
                        "please provide more context to uniquely identify the instance.\n"
                        f"String: {old_string}"
                    )
                )

            actual_new_string = file_edit_support.preserve_quote_style(
                normalized_old,
                actual_old_string,
                normalized_new,
            )
            updated_file = file_edit_support.apply_edit_to_file(
                text_meta.content,
                actual_old_string,
                actual_new_string,
                replace_all=bool(replace_all),
            )
            if updated_file == text_meta.content:
                return ToolExecutionResult(
                    content="Original and edited file match exactly. Failed to apply edit."
                )

            file_edit_support.write_text_with_metadata(
                str(resolved),
                updated_file,
                encoding=text_meta.encoding,
                line_endings=text_meta.line_endings,
            )
            return self._build_edit_result(
                resolved=resolved,
                original_file=text_meta.content,
                old_string=actual_old_string,
                new_string=new_string,
                updated_file=updated_file,
                replace_all=bool(replace_all),
            )
        except PermissionError as exc:
            return ToolExecutionResult(content=f"Error: {exc}")
        except Exception as exc:
            return ToolExecutionResult(content=f"Edit failed: {exc}")

    def _build_edit_result(
        self,
        *,
        resolved: Path,
        original_file: str,
        old_string: str,
        new_string: str,
        updated_file: str,
        replace_all: bool,
    ) -> ToolExecutionResult:
        data = {
            "filePath": str(resolved),
            "oldString": old_string,
            "newString": new_string,
            "originalFile": original_file,
            "structuredPatch": _build_structured_patch(original_file, updated_file),
            "userModified": False,
            "replaceAll": replace_all,
        }

        ctx = get_current_tool_runtime_context()
        if ctx is not None:
            current_mtime_ms = int(resolved.stat().st_mtime * 1000)
            updated_meta = file_edit_support.read_text_file_with_metadata(str(resolved))
            ctx.file_reads.record(
                FileReadSnapshot(
                    file_path=str(resolved),
                    timestamp_ms=int(time.time() * 1000),
                    file_mtime_ms=current_mtime_ms,
                    is_partial_view=False,
                    content_type="text",
                    content=updated_file,
                    offset=None,
                    limit=None,
                    pages=None,
                    encoding=updated_meta.encoding,
                    line_endings=updated_meta.line_endings,
                )
            )

        if replace_all:
            content = f"The file {resolved} has been updated. All occurrences were successfully replaced."
        else:
            content = f"The file {resolved} has been updated successfully."
        return ToolExecutionResult(content=content, data=data)


ReadFileTool = ReadTool
WriteFileTool = WriteTool

_HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_lines>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_lines>\d+))? @@"
)


def _normalize_default_text_read_args(
    offset: int | None,
    limit: int | None,
) -> tuple[int | None, int | None]:
    normalized_offset = offset
    normalized_limit = limit
    if normalized_offset == 0:
        normalized_offset = None
    if normalized_limit == file_read_support.MAX_LINES_TO_READ:
        normalized_limit = None
    return normalized_offset, normalized_limit


def _is_partial_read_view(
    *,
    content: str | None,
    content_type: str,
    offset: int | None,
    limit: int | None,
    pages: str | None,
) -> bool:
    if pages:
        return True
    if content_type != "text" or content is None:
        return offset is not None or limit is not None

    total_lines = len(content.splitlines())
    start = max(0, int(offset or 0))
    if start > 0:
        return True
    if limit is None:
        return False
    return int(limit) < total_lines


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
