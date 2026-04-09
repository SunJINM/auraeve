from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from auraeve.agent.context import ContextBuilder
from auraeve.agent.tools.assembler import build_tool_registry
from auraeve.agent.tools.base import ToolExecutionResult
from auraeve.agent.tools.search import GlobTool, GrepTool
from auraeve.agent.tools import search as search_module


def test_grep_tool_exposes_claude_style_parameters() -> None:
    tool = GrepTool()

    assert tool.name == "Grep"
    assert "ALWAYS use Grep for search tasks" in tool.description
    assert "NEVER invoke `grep` or `rg` as a Bash command" in tool.description
    assert 'Output modes: "content" shows matching lines, "files_with_matches" shows only file paths (default), "count" shows match counts' in tool.description
    assert tool.parameters["required"] == ["pattern"]
    props = tool.parameters["properties"]
    assert set(props) >= {
        "pattern",
        "path",
        "glob",
        "output_mode",
        "-B",
        "-A",
        "-C",
        "context",
        "-n",
        "-i",
        "type",
        "head_limit",
        "offset",
        "multiline",
    }


def test_glob_tool_exposes_claude_style_parameters() -> None:
    tool = GlobTool()

    assert tool.name == "Glob"
    assert "Fast file pattern matching tool" in tool.description
    assert "Use this tool when you need to find files by name patterns" in tool.description
    assert "open ended search that may require multiple rounds" in tool.description
    assert tool.parameters["required"] == ["pattern"]
    props = tool.parameters["properties"]
    assert set(props) == {"pattern", "path"}


def test_registry_and_prompt_include_grep_and_glob(tmp_path: Path) -> None:
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
        task_mode="legacy_todo",
        task_session_key="webui:chat-1",
    )

    assert registry.has("Grep")
    assert registry.has("Glob")
    assert registry.has("grep") is False
    assert registry.has("glob") is False

    prompt = ContextBuilder(tmp_path).build_system_prompt(
        channel="webui",
        chat_id="chat-1",
        available_tools={"Read", "Write", "Edit", "Grep", "Glob", "Bash"},
    )

    assert "- Grep: 搜索文件内容（ripgrep）" in prompt
    assert "- Glob: 按模式匹配文件路径" in prompt
    assert "内容搜索优先用 Grep，按文件名/路径模式查找优先用 Glob" in prompt
    assert "不要用 Bash 调用 rg、grep、find 或 dir 来替代" in prompt
    assert "第一次调用就尽量提供 path、glob、type 或 output_mode 这类约束" in prompt
    assert "开放式、多轮、发散式搜索任务，优先使用 agent" in prompt


@pytest.mark.asyncio
async def test_grep_tool_files_with_matches_and_content_modes(tmp_path: Path) -> None:
    import os

    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("alpha\nneedle\nomega\n", encoding="utf-8")
    (src / "b.py").write_text("needle again\n", encoding="utf-8")
    (src / "c.txt").write_text("needle txt\n", encoding="utf-8")
    os.utime(src / "a.py", (1_700_000_000, 1_700_000_000))
    os.utime(src / "b.py", (1_700_000_001, 1_700_000_001))

    tool = GrepTool(working_dir=str(tmp_path))

    files_result = await tool.execute(
        pattern="needle",
        path=str(src),
        glob="*.py",
        output_mode="files_with_matches",
    )
    assert isinstance(files_result, ToolExecutionResult)
    assert files_result.data["mode"] == "files_with_matches"
    assert files_result.data["numFiles"] == 2
    assert files_result.data["filenames"] == ["b.py", "a.py"]

    content_result = await tool.execute(
        pattern="needle",
        path=str(src),
        glob="*.py",
        output_mode="content",
        head_limit=1,
        offset=1,
    )
    assert isinstance(content_result, ToolExecutionResult)
    assert content_result.data["mode"] == "content"
    assert content_result.data["numLines"] == 1
    assert content_result.data["appliedOffset"] == 1
    assert content_result.content in {"a.py:2:needle", "b.py:1:needle again"}


@pytest.mark.asyncio
async def test_glob_tool_returns_mtime_sorted_matches(tmp_path: Path) -> None:
    files = [
        tmp_path / "old.log",
        tmp_path / "middle.log",
        tmp_path / "new.log",
    ]
    for index, file_path in enumerate(files):
        file_path.write_text(file_path.name, encoding="utf-8")
        ts = 1_700_000_000 + index
        Path(file_path).touch()
        import os
        os.utime(file_path, (ts, ts))

    tool = GlobTool(working_dir=str(tmp_path))
    result = await tool.execute(pattern="*.log", path=str(tmp_path))

    assert isinstance(result, ToolExecutionResult)
    assert result.data["numFiles"] == 3
    assert result.data["filenames"] == ["old.log", "middle.log", "new.log"]
    assert result.data["truncated"] is False


def test_resolve_rg_uses_builtin_when_forced(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    vendor_root = tmp_path / "vendor" / "ripgrep" / "x86_64-win32"
    vendor_root.mkdir(parents=True)
    builtin_rg = vendor_root / "rg.exe"
    builtin_rg.write_text("stub", encoding="utf-8")

    monkeypatch.setenv("USE_BUILTIN_RIPGREP", "1")
    monkeypatch.setattr(search_module, "_RIPGREP_VENDOR_ROOT", vendor_root.parent)
    monkeypatch.setattr(search_module.shutil, "which", lambda name: None)

    assert search_module._resolve_rg() == str(builtin_rg)


@pytest.mark.asyncio
async def test_grep_rejects_unc_paths_without_touching_filesystem(tmp_path: Path) -> None:
    tool = GrepTool(working_dir=str(tmp_path))

    result = await tool.execute(pattern="needle", path="\\\\server\\share\\repo")

    assert result.content == "Error: UNC paths are not allowed for Grep/Glob"


@pytest.mark.asyncio
async def test_grep_excludes_vcs_directories_by_default(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("needle in git metadata\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("needle in source\n", encoding="utf-8")

    tool = GrepTool(working_dir=str(tmp_path))
    result = await tool.execute(pattern="needle", path=str(tmp_path), output_mode="files_with_matches")

    assert result.data["filenames"] == ["src/app.py"]
