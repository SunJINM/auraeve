from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from auraeve.agent.tools.assembler import build_tool_registry
from auraeve.agent.tools.base import ToolExecutionResult
from auraeve.agent.tools.filesystem import EditTool, ReadTool
from auraeve.agent_runtime.tool_runtime_context import (
    FileReadStateStore,
    ToolRuntimeContext,
    use_tool_runtime_context,
)


def _make_ctx() -> ToolRuntimeContext:
    return ToolRuntimeContext(file_reads=FileReadStateStore())


@pytest.mark.asyncio
async def test_edit_tool_requires_existing_file_to_be_read_first(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("hello\n", encoding="utf-8")
    tool = EditTool(allowed_dir=tmp_path)

    with use_tool_runtime_context(_make_ctx()):
        result = await tool.execute(
            file_path=str(target.resolve()),
            old_string="hello",
            new_string="world",
        )

    assert isinstance(result, ToolExecutionResult)
    assert "Read" in result.content
    assert target.read_text(encoding="utf-8") == "hello\n"


@pytest.mark.asyncio
async def test_edit_tool_rejects_partial_read(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("a\nb\nc\n", encoding="utf-8")
    read_tool = ReadTool(allowed_dir=tmp_path)
    edit_tool = EditTool(allowed_dir=tmp_path)

    with use_tool_runtime_context(_make_ctx()):
        await read_tool.execute(file_path=str(target.resolve()), offset=0, limit=1)
        result = await edit_tool.execute(
            file_path=str(target.resolve()),
            old_string="b",
            new_string="B",
        )

    assert isinstance(result, ToolExecutionResult)
    assert "partially read" in result.content


@pytest.mark.asyncio
async def test_edit_tool_allows_read_with_explicit_default_full_read_params(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("hello\nworld\n", encoding="utf-8")
    read_tool = ReadTool(allowed_dir=tmp_path)
    edit_tool = EditTool(allowed_dir=tmp_path)

    with use_tool_runtime_context(_make_ctx()):
        await read_tool.execute(
            file_path=str(target.resolve()),
            offset=0,
            limit=2000,
            pages="",
        )
        result = await edit_tool.execute(
            file_path=str(target.resolve()),
            old_string="hello",
            new_string="HELLO",
        )

    assert isinstance(result, ToolExecutionResult)
    assert "updated successfully" in result.content
    assert target.read_text(encoding="utf-8") == "HELLO\nworld\n"


@pytest.mark.asyncio
async def test_edit_tool_allows_explicit_limit_that_covers_entire_file(tmp_path: Path) -> None:
    target = tmp_path / "heartbeat.md"
    target.write_text("".join(f"line {idx}\n" for idx in range(1, 17)), encoding="utf-8")
    read_tool = ReadTool(allowed_dir=tmp_path)
    edit_tool = EditTool(allowed_dir=tmp_path)

    with use_tool_runtime_context(_make_ctx()):
        await read_tool.execute(file_path=str(target.resolve()), offset=0, limit=16)
        result = await edit_tool.execute(
            file_path=str(target.resolve()),
            old_string="line 1\nline 2",
            new_string="LINE 1\nline 2",
        )

    assert isinstance(result, ToolExecutionResult)
    assert "updated successfully" in result.content
    assert target.read_text(encoding="utf-8").startswith("LINE 1\n")


@pytest.mark.asyncio
async def test_edit_tool_replaces_unique_match_and_returns_structured_result(
    tmp_path: Path,
) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("hello\nworld\n", encoding="utf-8")
    read_tool = ReadTool(allowed_dir=tmp_path)
    edit_tool = EditTool(allowed_dir=tmp_path)
    ctx = _make_ctx()

    with use_tool_runtime_context(ctx):
        await read_tool.execute(file_path=str(target.resolve()))
        result = await edit_tool.execute(
            file_path=str(target.resolve()),
            old_string="hello",
            new_string="HELLO",
        )

    assert isinstance(result, ToolExecutionResult)
    assert result.data["filePath"] == str(target.resolve())
    assert result.data["oldString"] == "hello"
    assert result.data["newString"] == "HELLO"
    assert result.data["replaceAll"] is False
    assert result.data["originalFile"] == "hello\nworld\n"
    assert isinstance(result.data["structuredPatch"], list)
    assert target.read_text(encoding="utf-8") == "HELLO\nworld\n"
    snapshot = ctx.file_reads.get(str(target.resolve()))
    assert snapshot is not None
    assert snapshot.content == "HELLO\nworld\n"


@pytest.mark.asyncio
async def test_edit_tool_rejects_identical_old_and_new_string(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("hello\n", encoding="utf-8")
    read_tool = ReadTool(allowed_dir=tmp_path)
    edit_tool = EditTool(allowed_dir=tmp_path)

    with use_tool_runtime_context(_make_ctx()):
        await read_tool.execute(file_path=str(target.resolve()))
        result = await edit_tool.execute(
            file_path=str(target.resolve()),
            old_string="hello",
            new_string="hello",
        )

    assert isinstance(result, ToolExecutionResult)
    assert "old_string and new_string are exactly the same" in result.content


@pytest.mark.asyncio
async def test_edit_tool_requires_replace_all_for_multiple_matches(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("x = 1\nx = x + 1\n", encoding="utf-8")
    read_tool = ReadTool(allowed_dir=tmp_path)
    edit_tool = EditTool(allowed_dir=tmp_path)

    with use_tool_runtime_context(_make_ctx()):
        await read_tool.execute(file_path=str(target.resolve()))
        result = await edit_tool.execute(
            file_path=str(target.resolve()),
            old_string="x",
            new_string="value",
        )

    assert isinstance(result, ToolExecutionResult)
    assert "replace_all" in result.content
    assert target.read_text(encoding="utf-8") == "x = 1\nx = x + 1\n"


@pytest.mark.asyncio
async def test_edit_tool_supports_replace_all(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("x = 1\nx = x + 1\n", encoding="utf-8")
    read_tool = ReadTool(allowed_dir=tmp_path)
    edit_tool = EditTool(allowed_dir=tmp_path)

    with use_tool_runtime_context(_make_ctx()):
        await read_tool.execute(file_path=str(target.resolve()))
        result = await edit_tool.execute(
            file_path=str(target.resolve()),
            old_string="x",
            new_string="value",
            replace_all=True,
        )

    assert isinstance(result, ToolExecutionResult)
    assert result.data["replaceAll"] is True
    assert "All occurrences" in result.content
    assert target.read_text(encoding="utf-8") == "value = 1\nvalue = value + 1\n"


@pytest.mark.asyncio
async def test_edit_tool_detects_stale_file_after_read(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("hello\n", encoding="utf-8")
    read_tool = ReadTool(allowed_dir=tmp_path)
    edit_tool = EditTool(allowed_dir=tmp_path)

    with use_tool_runtime_context(_make_ctx()):
        await read_tool.execute(file_path=str(target.resolve()))
        target.write_text("hello there\n", encoding="utf-8")
        result = await edit_tool.execute(
            file_path=str(target.resolve()),
            old_string="hello",
            new_string="world",
        )

    assert isinstance(result, ToolExecutionResult)
    assert "modified" in result.content.lower()


@pytest.mark.asyncio
async def test_edit_tool_can_create_missing_file_with_empty_old_string(
    tmp_path: Path,
) -> None:
    target = tmp_path / "new.txt"
    tool = EditTool(allowed_dir=tmp_path)

    with use_tool_runtime_context(_make_ctx()):
        result = await tool.execute(
            file_path=str(target.resolve()),
            old_string="",
            new_string="hello\n",
        )

    assert isinstance(result, ToolExecutionResult)
    assert target.read_text(encoding="utf-8") == "hello\n"
    assert result.data["originalFile"] == ""


@pytest.mark.asyncio
async def test_edit_tool_rejects_notebook_files(tmp_path: Path) -> None:
    target = tmp_path / "demo.ipynb"
    target.write_text(json.dumps({"cells": []}), encoding="utf-8")
    tool = EditTool(allowed_dir=tmp_path)

    with use_tool_runtime_context(_make_ctx()):
        result = await tool.execute(
            file_path=str(target.resolve()),
            old_string="{}",
            new_string='{"cells": []}',
        )

    assert isinstance(result, ToolExecutionResult)
    assert "Notebook" in result.content or "ipynb" in result.content


@pytest.mark.asyncio
async def test_edit_tool_preserves_crlf_line_endings(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_bytes(b"hello\r\nworld\r\n")
    read_tool = ReadTool(allowed_dir=tmp_path)
    edit_tool = EditTool(allowed_dir=tmp_path)

    with use_tool_runtime_context(_make_ctx()):
        await read_tool.execute(file_path=str(target.resolve()))
        await edit_tool.execute(
            file_path=str(target.resolve()),
            old_string="hello",
            new_string="HELLO",
        )

    assert target.read_bytes() == b"HELLO\r\nworld\r\n"


@pytest.mark.asyncio
async def test_edit_tool_preserves_curly_quote_style(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("print(“hello”)\n", encoding="utf-8")
    read_tool = ReadTool(allowed_dir=tmp_path)
    edit_tool = EditTool(allowed_dir=tmp_path)

    with use_tool_runtime_context(_make_ctx()):
        await read_tool.execute(file_path=str(target.resolve()))
        await edit_tool.execute(
            file_path=str(target.resolve()),
            old_string='print("hello")',
            new_string='print("world")',
        )

    assert target.read_text(encoding="utf-8") == "print(“world”)\n"


def test_edit_tool_schema_matches_claude_shape(tmp_path: Path) -> None:
    tool = EditTool(allowed_dir=tmp_path)

    assert tool.name == "Edit"
    assert set(tool.parameters["properties"]) == {
        "file_path",
        "old_string",
        "new_string",
        "replace_all",
    }
    assert tool.parameters["required"] == ["file_path", "old_string", "new_string"]


def test_build_tool_registry_registers_edit_without_legacy_name(
    tmp_path: Path,
) -> None:
    registry = build_tool_registry(
        profile="main",
        workspace=tmp_path,
        restrict_to_workspace=False,
        exec_timeout=5,
        brave_api_key=None,
        bus_publish_outbound=AsyncMock(),
        provider=MagicMock(),
        model="test-model",
        plan_manager=MagicMock(),
        task_mode="none",
    )

    assert registry.has("Edit")
    assert registry.has("edit_file") is False
