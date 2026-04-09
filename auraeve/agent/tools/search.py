from __future__ import annotations

import asyncio
import os
import platform
import re
import shutil
import time
from pathlib import Path
from typing import Any

from auraeve.agent.tools.base import Tool, ToolExecutionResult

_DEFAULT_GLOB_LIMIT = 100
_DEFAULT_GREP_HEAD_LIMIT = 250
_GLOB_CHARS_RE = re.compile(r"[*?[{]")
_SEARCH_MAX_COLUMNS = 500
_VCS_DIRECTORIES_TO_EXCLUDE = (".git", ".svn", ".hg", ".bzr", ".jj", ".sl")
_RIPGREP_VENDOR_ROOT = Path(__file__).resolve().parents[2] / "vendor" / "ripgrep"


def _env_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() not in {"", "0", "false", "no", "off"}


def _prefer_builtin_ripgrep() -> bool:
    return _env_truthy(os.getenv("USE_BUILTIN_RIPGREP"))


def _platform_ripgrep_dirname() -> str:
    machine = platform.machine().lower()
    arch_map = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "x64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    arch = arch_map.get(machine, machine)
    if os.name == "nt":
        return f"{arch}-win32"
    if platform.system() == "Darwin":
        return f"{arch}-darwin"
    return f"{arch}-linux"


def _builtin_rg_path() -> Path:
    executable = "rg.exe" if os.name == "nt" else "rg"
    return _RIPGREP_VENDOR_ROOT / _platform_ripgrep_dirname() / executable


def _is_unc_path(path: str) -> bool:
    return path.startswith("\\\\") or path.startswith("//")


def _resolve_rg() -> str:
    builtin_path = _builtin_rg_path()
    if _prefer_builtin_ripgrep():
        if builtin_path.exists():
            return str(builtin_path)
        raise FileNotFoundError(f"Configured builtin ripgrep not found: {builtin_path}")

    rg_path = shutil.which("rg")
    if rg_path:
        return rg_path
    if builtin_path.exists():
        return str(builtin_path)
    raise FileNotFoundError(
        "ripgrep (rg) is required for Grep/Glob tools. Install rg or provide "
        f"a vendored binary at {builtin_path}"
    )


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _resolve_search_target(
    raw_path: str | None,
    *,
    default_root: Path,
    allowed_dir: Path | None,
    require_directory: bool = False,
) -> tuple[Path, Path]:
    if raw_path and _is_unc_path(raw_path):
        raise PermissionError("UNC paths are not allowed for Grep/Glob")
    target = Path(raw_path).expanduser().resolve() if raw_path else default_root.resolve()
    if allowed_dir is not None and not target.is_relative_to(allowed_dir.resolve()):
        raise PermissionError(f"path {target} escapes allowed dir {allowed_dir}")
    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {target}")
    if require_directory and not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {target}")
    root = target if target.is_dir() else target.parent
    return target, root


def _extract_glob_base_directory(pattern: str) -> tuple[str, str]:
    match = _GLOB_CHARS_RE.search(pattern)
    if not match:
        path = Path(pattern)
        return str(path.parent), path.name
    prefix = pattern[: match.start()]
    last_sep = max(prefix.rfind("/"), prefix.rfind("\\"))
    if last_sep == -1:
        return "", pattern
    base_dir = prefix[:last_sep] or os.path.sep
    relative_pattern = pattern[last_sep + 1 :]
    return base_dir, relative_pattern


async def _run_rg(
    args: list[str],
    *,
    cwd: Path,
) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        _resolve_rg(),
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return (
        int(process.returncode or 0),
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def _append_default_search_exclusions(args: list[str]) -> None:
    for directory in _VCS_DIRECTORIES_TO_EXCLUDE:
        args.extend(["--glob", f"!{directory}"])


def _glob_no_ignore_enabled() -> bool:
    raw_value = os.getenv("CLAUDE_CODE_GLOB_NO_IGNORE", "true")
    return _env_truthy(raw_value)


def _glob_hidden_enabled() -> bool:
    raw_value = os.getenv("CLAUDE_CODE_GLOB_HIDDEN", "true")
    return _env_truthy(raw_value)


def _apply_head_limit(items: list[str], head_limit: int | None, offset: int) -> tuple[list[str], int | None]:
    if head_limit == 0:
        return items[offset:], None
    effective_limit = _DEFAULT_GREP_HEAD_LIMIT if head_limit is None else head_limit
    sliced = items[offset : offset + effective_limit]
    applied_limit = effective_limit if len(items) - offset > effective_limit else None
    return sliced, applied_limit


class GrepTool(Tool):
    def __init__(
        self,
        *,
        working_dir: str | None = None,
        allowed_dir: Path | None = None,
    ) -> None:
        self.working_dir = Path(working_dir or os.getcwd()).expanduser().resolve()
        self.allowed_dir = allowed_dir.resolve() if allowed_dir is not None else None

    @property
    def name(self) -> str:
        return "Grep"

    @property
    def description(self) -> str:
        return (
            "A powerful search tool built on ripgrep.\n\n"
            "Usage:\n"
            "- ALWAYS use Grep for search tasks. NEVER invoke `grep` or `rg` as a Bash command.\n"
            "- Supports full regex syntax.\n"
            "- Filter files with glob or type.\n"
            '- Output modes: "content" shows matching lines, "files_with_matches" shows only file paths (default), "count" shows match counts.\n'
            "- Use agent for open-ended searches requiring multiple rounds.\n"
            "- Use multiline=true for cross-line patterns."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for."},
                "path": {"type": "string", "description": "File or directory to search in."},
                "glob": {"type": "string", "description": "Glob pattern to filter files."},
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_with_matches", "count"],
                    "description": 'Output mode. Defaults to "files_with_matches".',
                },
                "-B": {"type": "integer", "minimum": 0},
                "-A": {"type": "integer", "minimum": 0},
                "-C": {"type": "integer", "minimum": 0},
                "context": {"type": "integer", "minimum": 0},
                "-n": {"type": "boolean"},
                "-i": {"type": "boolean"},
                "type": {"type": "string"},
                "head_limit": {"type": "integer", "minimum": 0},
                "offset": {"type": "integer", "minimum": 0},
                "multiline": {"type": "boolean"},
            },
            "required": ["pattern"],
        }

    @property
    def metadata(self) -> dict[str, Any]:
        return {"group": "filesystem", "search": True, "read_only": True}

    async def execute(self, pattern: str, **kwargs: Any) -> ToolExecutionResult:
        path = kwargs.get("path")
        output_mode = kwargs.get("output_mode") or "files_with_matches"
        head_limit = kwargs.get("head_limit")
        offset = int(kwargs.get("offset") or 0)
        try:
            target, root = _resolve_search_target(
                path,
                default_root=self.working_dir,
                allowed_dir=self.allowed_dir,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolExecutionResult(content=f"Error: {exc}")

        args = ["--hidden", "--max-columns", str(_SEARCH_MAX_COLUMNS)]
        _append_default_search_exclusions(args)
        if kwargs.get("multiline"):
            args.extend(["-U", "--multiline-dotall"])
        if kwargs.get("-i"):
            args.append("-i")
        if output_mode == "files_with_matches":
            args.append("-l")
        elif output_mode == "count":
            args.append("-c")
        elif kwargs.get("-n", True):
            args.append("-n")

        context_value = kwargs.get("context")
        if output_mode == "content":
            if context_value is not None:
                args.extend(["-C", str(context_value)])
            elif kwargs.get("-C") is not None:
                args.extend(["-C", str(kwargs["-C"])])
            else:
                if kwargs.get("-B") is not None:
                    args.extend(["-B", str(kwargs["-B"])])
                if kwargs.get("-A") is not None:
                    args.extend(["-A", str(kwargs["-A"])])

        if pattern.startswith("-"):
            args.extend(["-e", pattern])
        else:
            args.append(pattern)

        if kwargs.get("type"):
            args.extend(["--type", str(kwargs["type"])])
        if kwargs.get("glob"):
            raw_glob = str(kwargs["glob"])
            glob_patterns: list[str] = []
            for token in raw_glob.split():
                if "{" in token and "}" in token:
                    glob_patterns.append(token)
                else:
                    glob_patterns.extend(part for part in token.split(",") if part)
            for glob_pattern in glob_patterns:
                args.extend(["--glob", glob_pattern])

        target_arg = str(target)
        if target.is_relative_to(root):  # type: ignore[attr-defined]
            target_arg = str(target.relative_to(root))

        code, stdout, stderr = await _run_rg(args + [target_arg], cwd=root)
        if code not in {0, 1}:
            message = stderr.strip() or stdout.strip() or f"ripgrep failed with exit code {code}"
            return ToolExecutionResult(content=f"Error: {message}")

        raw_results = [line for line in stdout.strip().splitlines() if line.strip()]
        if output_mode == "content":
            normalized_lines: list[str] = []
            for line in raw_results:
                if ":" in line:
                    file_part, rest = line.split(":", 1)
                    normalized_lines.append(f"{_relative_to_root((root / file_part).resolve(), root)}:{rest}")
                else:
                    normalized_lines.append(line)
            limited_lines, applied_limit = _apply_head_limit(normalized_lines, head_limit, offset)
            content = "\n".join(limited_lines) if limited_lines else "No matches found"
            return ToolExecutionResult(
                content=content,
                data={
                    "mode": "content",
                    "numFiles": 0,
                    "filenames": [],
                    "content": content if limited_lines else "",
                    "numLines": len(limited_lines),
                    **({"appliedLimit": applied_limit} if applied_limit is not None else {}),
                    **({"appliedOffset": offset} if offset > 0 else {}),
                },
            )

        if output_mode == "count":
            normalized_lines: list[str] = []
            total_matches = 0
            for line in raw_results:
                if ":" not in line:
                    continue
                file_part, count_str = line.rsplit(":", 1)
                normalized_line = f"{_relative_to_root((root / file_part).resolve(), root)}:{count_str}"
                normalized_lines.append(normalized_line)
                try:
                    total_matches += int(count_str)
                except ValueError:
                    pass
            limited_lines, applied_limit = _apply_head_limit(normalized_lines, head_limit, offset)
            content = "\n".join(limited_lines) if limited_lines else "No matches found"
            return ToolExecutionResult(
                content=content,
                data={
                    "mode": "count",
                    "numFiles": len(limited_lines),
                    "filenames": [],
                    "content": content if limited_lines else "",
                    "numMatches": total_matches,
                    **({"appliedLimit": applied_limit} if applied_limit is not None else {}),
                    **({"appliedOffset": offset} if offset > 0 else {}),
                },
            )

        matches = [Path(line if os.path.isabs(line) else root / line).resolve() for line in raw_results]
        sorted_matches = sorted(
            matches,
            key=lambda item: (
                -(item.stat().st_mtime if item.exists() else 0),
                str(item),
            ),
        )
        limited_matches, applied_limit = _apply_head_limit(
            [_relative_to_root(match, root) for match in sorted_matches],
            head_limit,
            offset,
        )
        content = (
            "No files found"
            if not limited_matches
            else f"Found {len(limited_matches)} files\n" + "\n".join(limited_matches)
        )
        return ToolExecutionResult(
            content=content,
            data={
                "mode": "files_with_matches",
                "numFiles": len(limited_matches),
                "filenames": limited_matches,
                **({"appliedLimit": applied_limit} if applied_limit is not None else {}),
                **({"appliedOffset": offset} if offset > 0 else {}),
            },
        )


class GlobTool(Tool):
    def __init__(
        self,
        *,
        working_dir: str | None = None,
        allowed_dir: Path | None = None,
    ) -> None:
        self.working_dir = Path(working_dir or os.getcwd()).expanduser().resolve()
        self.allowed_dir = allowed_dir.resolve() if allowed_dir is not None else None

    @property
    def name(self) -> str:
        return "Glob"

    @property
    def description(self) -> str:
        return (
            "Fast file pattern matching tool that works with any codebase size.\n"
            "- Supports glob patterns like \"**/*.js\" or \"src/**/*.ts\".\n"
            "- Returns matching file paths sorted by modification time.\n"
            "- Use this tool when you need to find files by name patterns.\n"
            "- When you are doing an open ended search that may require multiple rounds of globbing and grepping, use the agent tool instead."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern to match."},
                "path": {"type": "string", "description": "Directory to search in."},
            },
            "required": ["pattern"],
        }

    @property
    def metadata(self) -> dict[str, Any]:
        return {"group": "filesystem", "search": True, "read_only": True}

    async def execute(self, pattern: str, path: str | None = None, **kwargs: Any) -> ToolExecutionResult:
        del kwargs
        search_pattern = pattern
        target_path = path
        if os.path.isabs(pattern):
            base_dir, relative_pattern = _extract_glob_base_directory(pattern)
            if base_dir:
                target_path = base_dir
                search_pattern = relative_pattern

        try:
            target, root = _resolve_search_target(
                target_path,
                default_root=self.working_dir,
                allowed_dir=self.allowed_dir,
                require_directory=True,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolExecutionResult(content=f"Error: {exc}")

        start = time.time()
        args = ["--files", "--glob", search_pattern, "--sort=modified"]
        if _glob_no_ignore_enabled():
            args.append("--no-ignore")
        if _glob_hidden_enabled():
            args.append("--hidden")
        _append_default_search_exclusions(args)
        code, stdout, stderr = await _run_rg(args + ["."], cwd=target)
        if code not in {0, 1}:
            message = stderr.strip() or stdout.strip() or f"ripgrep failed with exit code {code}"
            return ToolExecutionResult(content=f"Error: {message}")

        all_matches = [line for line in stdout.strip().splitlines() if line.strip()]
        files = [Path(target / match).resolve() for match in all_matches]
        truncated = len(files) > _DEFAULT_GLOB_LIMIT
        files = files[:_DEFAULT_GLOB_LIMIT]
        relative_files = [_relative_to_root(file_path, root) for file_path in files]
        content = (
            "No files found"
            if not relative_files
            else "\n".join(relative_files + (["(Results are truncated. Consider using a more specific path or pattern.)"] if truncated else []))
        )
        return ToolExecutionResult(
            content=content,
            data={
                "durationMs": int((time.time() - start) * 1000),
                "numFiles": len(relative_files),
                "filenames": relative_files,
                "truncated": truncated,
            },
        )
