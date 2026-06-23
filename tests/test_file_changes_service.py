"""FileChangesService 单元测试：git / 无 git / 未跟踪 / 越权 / 兜底。

完整独立：自带临时 git 仓库与 workspace 构造，无外部依赖。
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from auraeve.webui.file_changes_service import (
    FileChangesService,
    _parse_unified_diff,
    _reconstruct_before,
)


# ─── 辅助 ────────────────────────────────────────────────────────


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=str(cwd), check=True, capture_output=True)


def _init_git_repo(root: Path) -> None:
    _run(["git", "init"], root)
    _run(["git", "config", "user.email", "t@t.com"], root)
    _run(["git", "config", "user.name", "t"], root)
    _run(["git", "config", "commit.gpgsign", "false"], root)


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(not _git_available(), reason="git 不可用")


# ─── git 场景 ────────────────────────────────────────────────────


def test_git_modified_file_returns_diff(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    f = repo / "a.py"
    f.write_text("line1\nline2\nline3\n", encoding="utf-8")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-m", "init"], repo)
    f.write_text("line1\nLINE2\nline3\n", encoding="utf-8")

    svc = FileChangesService(tmp_path)
    res = asyncio.run(svc.compute(str(f)))

    assert res["git"] is True
    assert res["anchor"] == "a.py"
    paths = [item["path"] for item in res["files"]]
    assert "a.py" in paths
    entry = next(item for item in res["files"] if item["path"] == "a.py")
    assert entry["mode"] == "diff"
    assert entry["added"] == 1 and entry["removed"] == 1


def test_git_lists_all_changed_files_anchor_on_clicked(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    (repo / "a.py").write_text("a\n", encoding="utf-8")
    (repo / "b.py").write_text("b\n", encoding="utf-8")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-m", "init"], repo)
    (repo / "a.py").write_text("a2\n", encoding="utf-8")
    (repo / "b.py").write_text("b2\n", encoding="utf-8")

    svc = FileChangesService(tmp_path)
    res = asyncio.run(svc.compute(str(repo / "b.py")))

    paths = {item["path"] for item in res["files"]}
    assert {"a.py", "b.py"} <= paths
    assert res["anchor"] == "b.py"


def test_git_untracked_clicked_file_shown_as_full(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    (repo / "seed.py").write_text("seed\n", encoding="utf-8")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-m", "init"], repo)
    # 新建未跟踪文件（模拟 Agent 刚 Write 创建）
    new = repo / "new.py"
    new.write_text("hello\nworld\n", encoding="utf-8")

    svc = FileChangesService(tmp_path)
    res = asyncio.run(svc.compute(str(new), "", "hello\nworld\n"))

    assert res["anchor"] == "new.py"
    entry = next(item for item in res["files"] if item["path"] == "new.py")
    assert entry["status"] == "untracked"
    assert entry["mode"] == "full"
    # 全文件高亮：两行均为新增
    assert entry["added"] == 2


# ─── 无 git 场景 ─────────────────────────────────────────────────


def test_no_git_full_file_with_highlight(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    f = workspace / "note.txt"
    f.write_text("keep1\nNEW\nkeep2\n", encoding="utf-8")

    svc = FileChangesService(workspace)
    res = asyncio.run(svc.compute(str(f), "OLD", "NEW"))

    assert res["git"] is False
    assert len(res["files"]) == 1
    entry = res["files"][0]
    assert entry["mode"] == "full"
    types = [l["type"] for h in entry["hunks"] for l in h["lines"]]
    # keep1(ctx) OLD(del) NEW(add) keep2(ctx)
    assert "add" in types and "del" in types and "ctx" in types


def test_no_git_unlocatable_change_falls_back_to_plain(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    f = workspace / "note.txt"
    f.write_text("a\nb\nc\n", encoding="utf-8")

    svc = FileChangesService(workspace)
    # new_string 不在文件中 -> 退化为纯整文件（全 ctx）
    res = asyncio.run(svc.compute(str(f), "x", "not-present"))

    entry = res["files"][0]
    types = {l["type"] for h in entry["hunks"] for l in h["lines"]}
    assert types == {"ctx"}
    assert entry["added"] == 0 and entry["removed"] == 0


def test_escape_workspace_raises_permission(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret\n", encoding="utf-8")

    svc = FileChangesService(workspace)
    with pytest.raises(PermissionError):
        asyncio.run(svc.compute(str(outside)))


def test_missing_file_raises_not_found(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    svc = FileChangesService(workspace)
    with pytest.raises(FileNotFoundError):
        asyncio.run(svc.compute(str(workspace / "nope.txt")))


# ─── resolve_readable_path（原始字节端点的安全解析）────────────────


def test_resolve_readable_path_returns_workspace_file(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    f = workspace / "doc.md"
    f.write_text("# hi\n", encoding="utf-8")
    svc = FileChangesService(workspace)
    resolved = asyncio.run(svc.resolve_readable_path(str(f)))
    assert resolved == f.resolve()


def test_resolve_readable_path_escape_raises_permission(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "secret.bin"
    outside.write_text("x", encoding="utf-8")
    svc = FileChangesService(workspace)
    with pytest.raises(PermissionError):
        asyncio.run(svc.resolve_readable_path(str(outside)))


def test_resolve_readable_path_missing_raises_not_found(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    svc = FileChangesService(workspace)
    with pytest.raises(FileNotFoundError):
        asyncio.run(svc.resolve_readable_path(str(workspace / "nope.pdf")))


# ─── 纯函数 ──────────────────────────────────────────────────────


def test_reconstruct_before_replaces_first_occurrence() -> None:
    content = "x\nNEW\nNEW\n"
    assert _reconstruct_before(content, "OLD", "NEW") == "x\nOLD\nNEW\n"
    assert _reconstruct_before(content, "OLD", "MISSING") is None
    assert _reconstruct_before(content, "OLD", "") is None


def test_parse_unified_diff_tracks_line_numbers() -> None:
    diff = (
        "diff --git a/a.py b/a.py\n"
        "index 111..222 100644\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1,3 +1,3 @@\n"
        " line1\n"
        "-line2\n"
        "+LINE2\n"
        " line3\n"
    )
    files = _parse_unified_diff(diff)
    assert len(files) == 1
    f = files[0]
    assert f["path"] == "a.py"
    assert f["added"] == 1 and f["removed"] == 1
    lines = f["hunks"][0]["lines"]
    assert lines[0] == {"type": "ctx", "oldNo": 1, "newNo": 1, "text": "line1"}
    assert lines[1]["type"] == "del" and lines[1]["oldNo"] == 2
    assert lines[2]["type"] == "add" and lines[2]["newNo"] == 2
