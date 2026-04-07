from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import auraeve.config  # noqa: F401

from auraeve.agent.tools.assembler import build_tool_registry
from auraeve.agent.tools.base import ToolExecutionResult
from auraeve.agent.tools.filesystem import ReadTool, WriteTool
from auraeve.agent.tools.file_read_support import FILE_UNCHANGED_STUB
from auraeve.agent_runtime.tool_runtime_context import (
    FileReadStateStore,
    ToolRuntimeContext,
    use_tool_runtime_context,
)


@pytest.mark.asyncio
async def test_read_tool_returns_numbered_lines_with_offset_and_limit(
    tmp_path: Path,
) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("a\nb\nc\nd\n", encoding="utf-8")
    tool = ReadTool(allowed_dir=tmp_path)
    result = await tool.execute(file_path=str(target.resolve()), offset=1, limit=2)
    assert isinstance(result, ToolExecutionResult)
    assert "2\tb" in result.content
    assert "3\tc" in result.content
    assert "1\ta" not in result.content


@pytest.mark.asyncio
async def test_read_tool_returns_unchanged_stub_for_second_full_read(
    tmp_path: Path,
) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("hello\nworld\n", encoding="utf-8")
    tool = ReadTool(allowed_dir=tmp_path)
    with use_tool_runtime_context(ToolRuntimeContext(file_reads=FileReadStateStore())):
        first = await tool.execute(file_path=str(target.resolve()))
        second = await tool.execute(file_path=str(target.resolve()))
    assert isinstance(first, ToolExecutionResult)
    assert "1\thello" in first.content
    assert isinstance(second, ToolExecutionResult)
    assert second.content == FILE_UNCHANGED_STUB


@pytest.mark.asyncio
async def test_write_tool_rejects_existing_file_that_was_not_read(
    tmp_path: Path,
) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("old", encoding="utf-8")
    tool = WriteTool(allowed_dir=tmp_path)
    with use_tool_runtime_context(ToolRuntimeContext(file_reads=FileReadStateStore())):
        result = await tool.execute(file_path=str(target.resolve()), content="new")
    assert isinstance(result, ToolExecutionResult)
    assert "Read" in result.content
    assert target.read_text(encoding="utf-8") == "old"


@pytest.mark.asyncio
async def test_write_tool_allows_new_file_without_prior_read(tmp_path: Path) -> None:
    target = tmp_path / "new.txt"
    tool = WriteTool(allowed_dir=tmp_path)
    with use_tool_runtime_context(ToolRuntimeContext(file_reads=FileReadStateStore())):
        result = await tool.execute(file_path=str(target.resolve()), content="hello")
    assert isinstance(result, ToolExecutionResult)
    assert result.data["type"] == "create"
    assert "created successfully" in result.content.lower()
    assert target.read_text(encoding="utf-8") == "hello"


@pytest.mark.asyncio
async def test_write_tool_returns_structured_update_and_refreshes_read_state(
    tmp_path: Path,
) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("old\ntext\n", encoding="utf-8")
    read_tool = ReadTool(allowed_dir=tmp_path)
    write_tool = WriteTool(allowed_dir=tmp_path)
    ctx = ToolRuntimeContext(file_reads=FileReadStateStore())
    with use_tool_runtime_context(ctx):
        read_result = await read_tool.execute(file_path=str(target.resolve()))
        write_result = await write_tool.execute(file_path=str(target.resolve()), content="new\ntext\n")
    assert isinstance(read_result, ToolExecutionResult)
    assert isinstance(write_result, ToolExecutionResult)
    assert write_result.data["type"] == "update"
    assert write_result.data["filePath"] == str(target.resolve())
    assert write_result.data["originalFile"] == "old\ntext\n"
    assert write_result.data["content"] == "new\ntext\n"
    assert isinstance(write_result.data["structuredPatch"], list)
    snapshot = ctx.file_reads.get(str(target.resolve()))
    assert snapshot is not None
    assert snapshot.content == "new\ntext\n"
    assert snapshot.offset is None
    assert snapshot.limit is None


def test_build_tool_registry_registers_read_write_without_legacy_names(
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

    assert registry.has("Read")
    assert registry.has("Write")
    assert registry.has("Edit")
    assert registry.has("read_file") is False
    assert registry.has("write_file") is False
    assert registry.has("list_dir") is False
    assert registry.has("pdf") is False


@pytest.mark.asyncio
async def test_read_tool_returns_structured_image_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image_path = tmp_path / "demo.png"
    image_path.write_bytes(b"fake")

    async def _fake_image_reader(_path: str):
        return ToolExecutionResult(
            content=f"Image read successfully: {_path}",
            extra_messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Image file: {_path}"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                    ],
                }
            ],
            data={"type": "image", "filePath": _path},
        )

    monkeypatch.setattr(
        "auraeve.agent.tools.file_read_support.read_image_file",
        _fake_image_reader,
    )
    tool = ReadTool(allowed_dir=tmp_path)
    result = await tool.execute(file_path=str(image_path.resolve()))
    assert isinstance(result, ToolExecutionResult)
    assert result.data["type"] == "image"
    assert result.extra_messages[0]["content"][1]["type"] == "image_url"


@pytest.mark.asyncio
async def test_read_tool_requires_pages_for_large_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(
        "auraeve.agent.tools.file_read_support.get_pdf_page_count",
        lambda _path: 12,
    )
    tool = ReadTool(allowed_dir=tmp_path)
    result = await tool.execute(file_path=str(pdf_path.resolve()))
    assert isinstance(result, ToolExecutionResult)
    assert "pages" in result.content


@pytest.mark.asyncio
async def test_read_tool_honors_pdf_pages_parameter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    async def _fake_pdf_reader(_path: str, pages: str | None):
        return ToolExecutionResult(
            content=f"PDF pages loaded: {pages}",
            extra_messages=[],
            data={"type": "parts", "pages": pages},
        )

    monkeypatch.setattr(
        "auraeve.agent.tools.file_read_support.read_pdf_file",
        _fake_pdf_reader,
    )
    tool = ReadTool(allowed_dir=tmp_path)
    result = await tool.execute(file_path=str(pdf_path.resolve()), pages="2-3")
    assert isinstance(result, ToolExecutionResult)
    assert result.data["pages"] == "2-3"


@pytest.mark.asyncio
async def test_read_tool_loads_notebook_cells(tmp_path: Path) -> None:
    nb_path = tmp_path / "demo.ipynb"
    nb_path.write_text(
        json.dumps(
            {
                "cells": [
                    {"cell_type": "markdown", "metadata": {}, "source": ["# Title"]},
                    {
                        "cell_type": "code",
                        "metadata": {},
                        "source": ["print('ok')"],
                        "outputs": [],
                    },
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )
    tool = ReadTool(allowed_dir=tmp_path)
    result = await tool.execute(file_path=str(nb_path.resolve()))
    assert isinstance(result, ToolExecutionResult)
    assert result.data["type"] == "notebook"
    assert result.data["cells"][0]["source"] == "# Title"
    assert result.data["cells"][1]["source"] == "print('ok')"
