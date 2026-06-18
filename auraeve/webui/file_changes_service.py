"""文件变更视图服务：为 WebUI 文件抽屉计算「整文件 / git diff」结构化数据。

两种场景：
- 文件位于 git 仓库内：执行 `git diff HEAD` 取整仓库工作区改动，解析为结构化 hunks，
  锚定到点击文件；点击文件若为未跟踪文件，则该文件单独按「整文件」模式展示。
- 文件不在 git 仓库内：读取整文件内容，用 old/new 字符串尽力定位标记变更行；
  定位不到则退化为纯整文件展示。
"""
from __future__ import annotations

import asyncio
import contextlib
import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

# 单文件读取上限，避免超大文件拖垮前端渲染
_MAX_FILE_LINES = 20000
_MAX_FILE_BYTES = 4 * 1024 * 1024
_GIT_TIMEOUT_S = 8.0


@dataclass
class _GitResult:
    ok: bool
    stdout: str
    returncode: int


async def _run_git(args: list[str], cwd: Path, timeout: float = _GIT_TIMEOUT_S) -> _GitResult:
    """执行 git 子进程，超时/失败返回 ok=False。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return _GitResult(ok=False, stdout="", returncode=-1)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"启动 git 失败：{exc}")
        return _GitResult(ok=False, stdout="", returncode=-1)
    try:
        stdout_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        return _GitResult(ok=False, stdout="", returncode=-1)
    return _GitResult(
        ok=proc.returncode == 0,
        stdout=stdout_b.decode("utf-8", errors="replace"),
        returncode=proc.returncode if proc.returncode is not None else -1,
    )


class FileChangesService:
    """计算文件抽屉所需的变更数据。受 workspace 边界与 git 仓库根约束。"""

    def __init__(self, workspace_dir: Path) -> None:
        self._workspace = workspace_dir.expanduser().resolve()

    # ─── 对外入口 ────────────────────────────────────────────────

    async def compute(
        self,
        raw_path: str,
        old_string: str | None = None,
        new_string: str | None = None,
    ) -> dict[str, Any]:
        """返回结构化变更数据；越权抛 PermissionError，文件缺失抛 FileNotFoundError。"""
        path = Path(raw_path).expanduser()
        try:
            path = path.resolve()
        except OSError:
            raise FileNotFoundError(raw_path)

        repo_root = await self._git_root(path)
        if repo_root is not None:
            return await self._compute_git(repo_root, path, old_string, new_string)

        # 无 git：仅允许 workspace 内的文件，避免任意路径读取
        self._ensure_within_workspace(path)
        return self._compute_no_git(path, old_string, new_string)

    # ─── git 场景 ────────────────────────────────────────────────

    async def _git_root(self, path: Path) -> Path | None:
        base = path if path.is_dir() else path.parent
        if not base.exists():
            return None
        res = await _run_git(["rev-parse", "--show-toplevel"], cwd=base)
        if not res.ok:
            return None
        root = res.stdout.strip()
        return Path(root).resolve() if root else None

    async def _compute_git(
        self,
        repo_root: Path,
        clicked: Path,
        old_string: str | None,
        new_string: str | None,
    ) -> dict[str, Any]:
        # 工作区 vs HEAD：覆盖已暂存 + 未暂存改动；不含未跟踪文件
        diff_res = await _run_git(["diff", "--no-color", "HEAD"], cwd=repo_root)
        files = _parse_unified_diff(diff_res.stdout) if diff_res.ok else []

        rel = _relpath_posix(clicked, repo_root)
        anchor = rel

        # 点击文件若不在 diff 列表中（未跟踪 / 已被还原），单独以整文件模式补入并置顶锚定
        if rel is not None and not any(f["path"] == rel for f in files):
            untracked = await self._is_untracked(repo_root, clicked)
            if untracked or clicked.exists():
                entry = self._build_full_file_entry(
                    clicked,
                    rel,
                    old_string,
                    new_string,
                    status="untracked" if untracked else "unchanged",
                )
                files.insert(0, entry)

        return {
            "git": True,
            "repoRoot": str(repo_root),
            "anchor": anchor,
            "files": files,
        }

    async def _is_untracked(self, repo_root: Path, path: Path) -> bool:
        res = await _run_git(
            ["ls-files", "--error-unmatch", "--", str(path)], cwd=repo_root
        )
        return not res.ok

    # ─── 无 git 场景 ─────────────────────────────────────────────

    def _compute_no_git(
        self,
        path: Path,
        old_string: str | None,
        new_string: str | None,
    ) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(str(path))
        entry = self._build_full_file_entry(
            path, str(path), old_string, new_string, status="modified"
        )
        return {
            "git": False,
            "repoRoot": None,
            "anchor": str(path),
            "files": [entry],
        }

    # ─── 整文件条目（无 git / 未跟踪 / 已还原 共用）─────────────

    def _build_full_file_entry(
        self,
        path: Path,
        display_path: str,
        old_string: str | None,
        new_string: str | None,
        *,
        status: str,
    ) -> dict[str, Any]:
        content, truncated = _read_text(path)
        before = _reconstruct_before(content, old_string, new_string)
        if before is None:
            # 定位不到变更：纯整文件展示（全部 ctx 行）
            lines = [
                {"type": "ctx", "oldNo": i + 1, "newNo": i + 1, "text": text}
                for i, text in enumerate(content.split("\n"))
            ]
            added = removed = 0
        else:
            lines, added, removed = _full_file_diff(before, content)

        return {
            "path": display_path,
            "status": status,
            "mode": "full",
            "added": added,
            "removed": removed,
            "truncated": truncated,
            "hunks": [{"header": None, "lines": lines}],
        }

    # ─── 安全 ────────────────────────────────────────────────────

    def _ensure_within_workspace(self, path: Path) -> None:
        if self._workspace == path or self._workspace in path.parents:
            return
        raise PermissionError(f"path {path} escapes workspace {self._workspace}")


# ─── 工具函数 ───────────────────────────────────────────────────


def _relpath_posix(path: Path, root: Path) -> str | None:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def _read_text(path: Path) -> tuple[str, bool]:
    """读取文本，超限截断。返回 (content, truncated)。"""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise FileNotFoundError(str(path)) from exc
    truncated = False
    if len(raw) > _MAX_FILE_BYTES:
        raw = raw[:_MAX_FILE_BYTES]
        truncated = True
    text = raw.decode("utf-8", errors="replace")
    # 归一化换行：磁盘可能是 CRLF，而工具的 old/new 串用 LF，统一后才能稳定定位高亮
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = text.split("\n")
    if len(parts) > _MAX_FILE_LINES:
        parts = parts[:_MAX_FILE_LINES]
        truncated = True
        text = "\n".join(parts)
    return text, truncated


def _reconstruct_before(
    content: str, old_string: str | None, new_string: str | None
) -> str | None:
    """用 old/new 还原变更前内容：把当前内容中首个 new_string 替换回 old_string。

    new_string 为空（纯删除场景无意义）或在当前内容中找不到时返回 None，由调用方退化。
    """
    if not new_string:
        return None
    if new_string not in content:
        return None
    return content.replace(new_string, old_string or "", 1)


def _full_file_diff(before: str, after: str) -> tuple[list[dict[str, Any]], int, int]:
    """整文件行级 diff（不裁剪上下文）。返回 (lines, added, removed)。"""
    a = before.split("\n")
    b = after.split("\n")
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    lines: list[dict[str, Any]] = []
    added = removed = 0
    old_no = new_no = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i1, i2):
                old_no += 1
                new_no += 1
                lines.append({"type": "ctx", "oldNo": old_no, "newNo": new_no, "text": a[k]})
        else:
            for k in range(i1, i2):
                old_no += 1
                removed += 1
                lines.append({"type": "del", "oldNo": old_no, "text": a[k]})
            for k in range(j1, j2):
                new_no += 1
                added += 1
                lines.append({"type": "add", "newNo": new_no, "text": b[k]})
    return lines, added, removed


def _parse_unified_diff(diff_text: str) -> list[dict[str, Any]]:
    """解析 `git diff` 统一格式为 [{path,status,mode:'diff',hunks:[...],added,removed}]。"""
    files: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    cur_hunk: dict[str, Any] | None = None
    old_no = new_no = 0

    def _flush_hunk() -> None:
        nonlocal cur_hunk
        if cur is not None and cur_hunk is not None:
            cur["hunks"].append(cur_hunk)
        cur_hunk = None

    def _flush_file() -> None:
        nonlocal cur
        _flush_hunk()
        if cur is not None:
            files.append(cur)
        cur = None

    for line in diff_text.split("\n"):
        if line.startswith("diff --git"):
            _flush_file()
            cur = {
                "path": "",
                "oldPath": None,
                "status": "modified",
                "mode": "diff",
                "added": 0,
                "removed": 0,
                "binary": False,
                "hunks": [],
            }
            continue
        if cur is None:
            continue
        if line.startswith("new file mode"):
            cur["status"] = "added"
            continue
        if line.startswith("deleted file mode"):
            cur["status"] = "deleted"
            continue
        if line.startswith("rename from "):
            cur["oldPath"] = line[len("rename from ") :].strip()
            cur["status"] = "renamed"
            continue
        if line.startswith("rename to "):
            cur["path"] = line[len("rename to ") :].strip()
            cur["status"] = "renamed"
            continue
        if line.startswith("Binary files"):
            cur["binary"] = True
            continue
        if line.startswith("--- "):
            old = line[4:].strip()
            cur["oldPath"] = None if old == "/dev/null" else _strip_ab(old)
            continue
        if line.startswith("+++ "):
            new = line[4:].strip()
            if new != "/dev/null":
                cur["path"] = _strip_ab(new)
            elif not cur["path"]:
                cur["path"] = cur["oldPath"] or ""
            continue
        if line.startswith("@@"):
            _flush_hunk()
            old_no, new_no = _parse_hunk_header(line)
            cur_hunk = {"header": line, "lines": []}
            continue
        if cur_hunk is None:
            continue
        if line.startswith("+"):
            cur_hunk["lines"].append({"type": "add", "newNo": new_no, "text": line[1:]})
            new_no += 1
            cur["added"] += 1
        elif line.startswith("-"):
            cur_hunk["lines"].append({"type": "del", "oldNo": old_no, "text": line[1:]})
            old_no += 1
            cur["removed"] += 1
        elif line.startswith("\\"):
            # "\ No newline at end of file" —— 忽略
            continue
        else:
            text = line[1:] if line.startswith(" ") else line
            cur_hunk["lines"].append(
                {"type": "ctx", "oldNo": old_no, "newNo": new_no, "text": text}
            )
            old_no += 1
            new_no += 1

    _flush_file()
    return files


def _strip_ab(path: str) -> str:
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def _parse_hunk_header(line: str) -> tuple[int, int]:
    """从 `@@ -a,b +c,d @@` 取起始旧/新行号。"""
    try:
        seg = line.split("@@")[1].strip()
        old_part, new_part = seg.split(" ")[:2]
        old_no = int(old_part[1:].split(",")[0])
        new_no = int(new_part[1:].split(",")[0])
        return old_no, new_no
    except (IndexError, ValueError):
        return 1, 1
