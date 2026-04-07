from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_DENY_PATTERNS = [
    r"\brm\s+-[rf]{1,2}\b",
    r"\bdel\s+/[fq]\b",
    r"\brmdir\s+/s\b",
    r"\b(format|mkfs|diskpart)\b",
    r"\bdd\s+if=",
    r">\s*/dev/sd",
    r"\b(shutdown|reboot|poweroff)\b",
    r":\(\)\s*\{.*\};\s*:",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+checkout\s+--\b",
    r"\bgit\s+restore\b.*(?:--staged|--source=)",
    r"\bgit\s+clean\s+-f\b",
]


@dataclass(slots=True)
class ShellCommandResult:
    stdout: str
    stderr: str
    code: int
    interrupted: bool
    backgroundTaskId: str | None = None
    backgroundedByUser: bool | None = None
    assistantAutoBackgrounded: bool | None = None
    outputFilePath: str | None = None
    outputFileSize: int | None = None
    outputTaskId: str | None = None
    preSpawnError: str | None = None
    cwd: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class _BackgroundShellTask:
    task_id: str
    process: asyncio.subprocess.Process
    output_file_path: str
    cwd_file_path: str
    cwd_path: str | None = None


_BACKGROUND_TASKS: dict[str, _BackgroundShellTask] = {}


def _resolve_path(path: str, allowed_dir: Path | None = None) -> Path:
    resolved = Path(path).expanduser().resolve()
    if allowed_dir and not str(resolved).startswith(str(allowed_dir.resolve())):
        raise PermissionError(f"path {path} escapes allowed dir {allowed_dir}")
    return resolved


def _check_path_exists(path: str) -> bool:
    return Path(path).exists()


def _find_git_bash_path() -> str:
    env_path = os.getenv("CLAUDE_CODE_GIT_BASH_PATH") or os.getenv("AURAEVE_GIT_BASH_PATH")
    if env_path:
        if _check_path_exists(env_path):
            return env_path
        raise FileNotFoundError(f"Configured Git Bash path not found: {env_path}")

    common_locations = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    ]
    for candidate in common_locations:
        if _check_path_exists(candidate):
            return candidate

    git_path = shutil.which("git")
    if git_path:
        candidate = Path(git_path).resolve().parent.parent / "bin" / "bash.exe"
        if candidate.exists():
            return str(candidate)

    raise FileNotFoundError(
        "AuraEve on Windows requires Git Bash. Install git-bash or set "
        "CLAUDE_CODE_GIT_BASH_PATH=C:\\Program Files\\Git\\bin\\bash.exe"
    )


def resolve_bash_executable() -> str:
    if os.name == "nt":
        return _find_git_bash_path()
    return shutil.which("bash") or "bash"


def windows_path_to_posix_path(windows_path: str) -> str:
    if windows_path.startswith("\\\\"):
        return windows_path.replace("\\", "/")
    match = re.match(r"^([A-Za-z]):[/\\](.*)$", windows_path)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2).replace("\\", "/")
        return f"/{drive}/{rest}"
    return windows_path.replace("\\", "/")


def posix_path_to_windows_path(posix_path: str) -> str:
    if posix_path.startswith("//"):
        return posix_path.replace("/", "\\")
    match = re.match(r"^/([A-Za-z])(?:/(.*))?$", posix_path)
    if match:
        drive = match.group(1).upper()
        rest = (match.group(2) or "").replace("/", "\\")
        return f"{drive}:\\{rest}" if rest else f"{drive}:\\"
    return posix_path.replace("/", "\\")


def _shell_quote(value: str) -> str:
    return shlex.quote(value)


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


def _build_bash_command(command: str, cwd: str) -> tuple[str, str]:
    native_tmp = tempfile.gettempdir()
    cwd_file_native = str(Path(native_tmp) / f"auraeve-bash-cwd-{uuid.uuid4().hex}.txt")
    cwd_file_shell = windows_path_to_posix_path(cwd_file_native) if os.name == "nt" else cwd_file_native
    shell_cwd = windows_path_to_posix_path(cwd) if os.name == "nt" else cwd
    command_string = (
        f"cd {_shell_quote(shell_cwd)} && "
        f"eval {_shell_quote(command)}; "
        "status=$?; "
        f"pwd -P >| {_shell_quote(cwd_file_shell)}; "
        "exit $status"
    )
    return command_string, cwd_file_native


async def _monitor_background_task(task_id: str) -> None:
    task = _BACKGROUND_TASKS.get(task_id)
    if task is None:
        return
    try:
        await task.process.wait()
    finally:
        cwd_path: str | None = None
        try:
            raw_cwd = Path(task.cwd_file_path).read_text(encoding="utf-8").strip()
            if raw_cwd:
                cwd_path = posix_path_to_windows_path(raw_cwd) if os.name == "nt" else raw_cwd
        except Exception:
            cwd_path = None
        task.cwd_path = cwd_path


async def execute_shell_command(
    *,
    command: str,
    timeout_ms: int = 60_000,
    working_dir: str | None = None,
    deny_patterns: list[str] | None = None,
    restrict_to_workspace: bool = False,
    run_in_background: bool = False,
    dangerously_disable_sandbox: bool = False,
) -> ShellCommandResult:
    del dangerously_disable_sandbox
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
        return ShellCommandResult(
            stdout="",
            stderr=guard_error,
            code=1,
            interrupted=False,
            preSpawnError=guard_error,
            cwd=cwd,
        )

    bash_path = resolve_bash_executable()
    command_string, cwd_file_path = _build_bash_command(command, cwd)

    try:
        if run_in_background:
            output_file = str(Path(tempfile.gettempdir()) / f"auraeve-bash-output-{uuid.uuid4().hex}.log")
            output_handle = open(output_file, "wb")
            try:
                process = await asyncio.create_subprocess_exec(
                    bash_path,
                    "-lc",
                    command_string,
                    stdout=output_handle,
                    stderr=output_handle,
                    cwd=cwd,
                )
            finally:
                output_handle.close()
            task_id = f"bash_{uuid.uuid4().hex[:12]}"
            _BACKGROUND_TASKS[task_id] = _BackgroundShellTask(
                task_id=task_id,
                process=process,
                output_file_path=output_file,
                cwd_file_path=cwd_file_path,
                cwd_path=None,
            )
            asyncio.create_task(_monitor_background_task(task_id))
            return ShellCommandResult(
                stdout="",
                stderr="",
                code=0,
                interrupted=False,
                backgroundTaskId=task_id,
                backgroundedByUser=True,
                outputFilePath=output_file,
                cwd=cwd,
            )

        process = await asyncio.create_subprocess_exec(
            bash_path,
            "-lc",
            command_string,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
    except Exception as exc:
        prefix = f"{cwd_warning}\n" if cwd_warning else ""
        error = f"{prefix}Error: failed to start command in {cwd}: {exc}"
        return ShellCommandResult(
            stdout="",
            stderr=error,
            code=1,
            interrupted=False,
            preSpawnError=error,
            cwd=cwd,
        )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=max(1, timeout_ms) / 1000)
    except asyncio.TimeoutError:
        process.kill()
        return ShellCommandResult(
            stdout="",
            stderr=f"Error: command timed out ({timeout_ms}ms)",
            code=124,
            interrupted=True,
            cwd=cwd,
        )

    resolved_cwd = cwd
    try:
        raw_cwd = Path(cwd_file_path).read_text(encoding="utf-8").strip()
        if raw_cwd:
            resolved_cwd = posix_path_to_windows_path(raw_cwd) if os.name == "nt" else raw_cwd
    except Exception:
        resolved_cwd = cwd
    finally:
        Path(cwd_file_path).unlink(missing_ok=True)

    stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
    stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""
    if cwd_warning:
        stderr_text = f"{cwd_warning}\n{stderr_text}".strip()
    return ShellCommandResult(
        stdout=stdout_text,
        stderr=stderr_text,
        code=int(process.returncode or 0),
        interrupted=False,
        cwd=resolved_cwd,
    )


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
