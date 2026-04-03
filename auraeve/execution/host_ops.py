from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path


DEFAULT_DENY_PATTERNS = [
    r"\brm\s+-[rf]{1,2}\b",
    r"\bdel\s+/[fq]\b",
    r"\brmdir\s+/s\b",
    r"\b(format|mkfs|diskpart)\b",
    r"\bdd\s+if=",
    r">\s*/dev/sd",
    r"\b(shutdown|reboot|poweroff)\b",
    r":\(\)\s*\{.*\};\s*:",
]


def _resolve_path(path: str, allowed_dir: Path | None = None) -> Path:
    resolved = Path(path).expanduser().resolve()
    if allowed_dir and not str(resolved).startswith(str(allowed_dir.resolve())):
        raise PermissionError(f"path {path} escapes allowed dir {allowed_dir}")
    return resolved


def guard_shell_command(
    command: str,
    cwd: str,
    *,
    deny_patterns: list[str] | None = None,
    restrict_to_workspace: bool = False,
) -> str | None:
    cmd = command.strip()
    lower = cmd.lower()
    for pattern in (deny_patterns or DEFAULT_DENY_PATTERNS):
        if re.search(pattern, lower):
            return "Error: command blocked by guard policy (dangerous operation detected)."
    if restrict_to_workspace:
        if "..\\" in cmd or "../" in cmd:
            return "Error: command blocked by guard policy (path traversal detected)."
        cwd_path = Path(cwd).resolve()
        win_paths = re.findall(r"[A-Za-z]:\\[^\\\"']+", cmd)
        posix_paths = re.findall(r"(?:^|[\s|>])(/[^\\s\"'>]+)", cmd)
        for raw in win_paths + posix_paths:
            try:
                p = Path(raw.strip()).resolve()
            except Exception:
                continue
            if p.is_absolute() and cwd_path not in p.parents and p != cwd_path:
                return "Error: command blocked by guard policy (path outside workspace)."
    return None


async def execute_shell_command(
    *,
    command: str,
    timeout: int = 60,
    working_dir: str | None = None,
    deny_patterns: list[str] | None = None,
    restrict_to_workspace: bool = False,
) -> str:
    cwd = working_dir or os.getcwd()
    cwd_warning: str | None = None
    try:
        cwd_path = Path(cwd).expanduser().resolve()
        if not cwd_path.exists() or not cwd_path.is_dir():
            fallback = Path(os.getcwd()).resolve()
            cwd_warning = f"Warning: working_dir not found or not a directory ({cwd}); fallback to {fallback}"
            cwd = str(fallback)
        else:
            cwd = str(cwd_path)
    except Exception:
        fallback = Path(os.getcwd()).resolve()
        cwd_warning = f"Warning: invalid working_dir ({cwd}); fallback to {fallback}"
        cwd = str(fallback)
    guard_error = guard_shell_command(
        command,
        cwd,
        deny_patterns=deny_patterns,
        restrict_to_workspace=restrict_to_workspace,
    )
    if guard_error:
        return guard_error
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
    except Exception as exc:
        prefix = f"{cwd_warning}\n" if cwd_warning else ""
        return f"{prefix}Error: failed to start command in {cwd}: {exc}"
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        return f"Error: command timed out ({timeout}s)"
    output_parts: list[str] = []
    if stdout:
        output_parts.append(stdout.decode("utf-8", errors="replace"))
    if stderr:
        stderr_text = stderr.decode("utf-8", errors="replace")
        if stderr_text.strip():
            output_parts.append(f"STDERR:\n{stderr_text}")
    if process.returncode != 0:
        output_parts.append(f"\nExitCode: {process.returncode}")
    result = "\n".join(output_parts) if output_parts else "(no output)"
    if cwd_warning:
        result = f"{cwd_warning}\n{result}"
    max_len = 10000
    if len(result) > max_len:
        result = result[:max_len] + f"\n...(truncated, {len(result) - max_len} chars omitted)"
    return result


def read_file(
    *,
    path: str,
    allowed_dir: Path | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> str:
    file_path = _resolve_path(path, allowed_dir)
    if not file_path.exists():
        return f"Error: file not found: {path}"
    if not file_path.is_file():
        return f"Error: not a file: {path}"
    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = int(offset or 0)
    count = int(limit or min(len(lines), 2000))
    selected = lines[start : start + count]
    return "\n".join(f"{start + idx + 1}\t{line}" for idx, line in enumerate(selected))


def write_file(
    *,
    path: str,
    content: str,
    allowed_dir: Path | None = None,
) -> tuple[str, str | None]:
    file_path = _resolve_path(path, allowed_dir)
    original = file_path.read_text(encoding="utf-8") if file_path.exists() else None
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return ("create" if original is None else "update"), original


def edit_file(
    *,
    path: str,
    old_text: str,
    new_text: str,
    allowed_dir: Path | None = None,
) -> str:
    file_path = _resolve_path(path, allowed_dir)
    if not file_path.exists():
        return f"Error: file not found: {path}"
    content = file_path.read_text(encoding="utf-8")
    if old_text not in content:
        return "Error: old_text not found in file"
    count = content.count(old_text)
    if count > 1:
        return f"Warning: old_text appears {count} times; provide more context"
    file_path.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
    return f"Edited {path}"


def list_dir(*, path: str, allowed_dir: Path | None = None) -> str:
    dir_path = _resolve_path(path, allowed_dir)
    if not dir_path.exists():
        return f"Error: directory not found: {path}"
    if not dir_path.is_dir():
        return f"Error: not a directory: {path}"
    items = []
    for item in sorted(dir_path.iterdir()):
        prefix = "[D] " if item.is_dir() else "[F] "
        items.append(f"{prefix}{item.name}")
    return "\n".join(items) if items else f"Directory {path} is empty"
