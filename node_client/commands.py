"""
本地节点支持的命令实现。

每个命令是一个 async 函数，接收 params: dict，返回 (ok: bool, output: str, error: str)。
"""

from __future__ import annotations

import asyncio
import base64
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# 命令注册表
# ─────────────────────────────────────────────────────────────────────────────

_REGISTRY: dict[str, Any] = {}


def command(name: str):
    """命令装饰器，将函数注册到命令表。"""
    def decorator(fn):
        _REGISTRY[name] = fn
        return fn
    return decorator


def list_commands() -> list[str]:
    return list(_REGISTRY.keys())


async def dispatch(cmd: str, params: dict) -> tuple[bool, str, str]:
    """
    分发命令到对应处理函数。
    返回 (ok, output, error)
    """
    handler = _REGISTRY.get(cmd)
    if handler is None:
        return False, "", f"未知命令：{cmd}"
    try:
        return await handler(params)
    except Exception as e:
        return False, "", f"命令执行异常：{e}"


# ─────────────────────────────────────────────────────────────────────────────
# Shell 命令
# ─────────────────────────────────────────────────────────────────────────────

@command("shell.run")
async def shell_run(params: dict) -> tuple[bool, str, str]:
    """
    执行 shell 命令。
    params: {cmd: str, cwd?: str, timeout?: int, env?: dict}
    """
    cmd = params.get("cmd", "")
    if not cmd:
        return False, "", "参数 cmd 不能为空"

    cwd = params.get("cwd") or None
    timeout = int(params.get("timeout", 60))
    extra_env = params.get("env") or {}

    env = {**os.environ, **{str(k): str(v) for k, v in extra_env.items()}}

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return False, "", f"命令超时（{timeout}s）：{cmd}"

        # Windows 编码处理
        encoding = "gbk" if sys.platform == "win32" else "utf-8"
        stdout = stdout_b.decode(encoding, errors="replace").rstrip()
        stderr = stderr_b.decode(encoding, errors="replace").rstrip()

        ok = proc.returncode == 0
        output = stdout
        if stderr:
            output = (output + "\n[stderr]\n" + stderr).strip() if output else stderr
        if proc.returncode != 0:
            output = (output + f"\n[exit code: {proc.returncode}]").strip()

        return ok, output, "" if ok else f"exit code {proc.returncode}"

    except FileNotFoundError as e:
        return False, "", f"命令未找到：{e}"


@command("shell.which")
async def shell_which(params: dict) -> tuple[bool, str, str]:
    """查找可执行文件路径。params: {name: str}"""
    name = params.get("name", "")
    if not name:
        return False, "", "参数 name 不能为空"

    import shutil
    path = shutil.which(name)
    if path:
        return True, path, ""
    return False, "", f"未找到：{name}"


# ─────────────────────────────────────────────────────────────────────────────
# 文件系统命令
# ─────────────────────────────────────────────────────────────────────────────

@command("fs.list")
async def fs_list(params: dict) -> tuple[bool, str, str]:
    """列出目录内容。params: {path: str}"""
    dir_path = Path(params.get("path", "."))
    try:
        entries = sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        lines = []
        for entry in entries:
            try:
                size = entry.stat().st_size if entry.is_file() else 0
                kind = "文件" if entry.is_file() else "目录"
                size_str = f"  {size:>10,} B" if entry.is_file() else ""
                lines.append(f"[{kind}]  {entry.name}{size_str}")
            except PermissionError:
                lines.append(f"[权限不足]  {entry.name}")
        return True, "\n".join(lines) or "（空目录）", ""
    except FileNotFoundError:
        return False, "", f"目录不存在：{dir_path}"
    except PermissionError:
        return False, "", f"权限不足：{dir_path}"


@command("fs.read")
async def fs_read(params: dict) -> tuple[bool, str, str]:
    """读取文件内容。params: {path: str, max_bytes?: int}"""
    file_path = Path(params.get("path", ""))
    max_bytes = int(params.get("max_bytes", 200_000))
    try:
        content = file_path.read_bytes()
        if len(content) > max_bytes:
            content = content[:max_bytes]
            suffix = f"\n[文件已截断，显示前 {max_bytes} 字节]"
        else:
            suffix = ""
        # 尝试 UTF-8 解码，失败则 base64
        try:
            text = content.decode("utf-8") + suffix
            return True, text, ""
        except UnicodeDecodeError:
            b64 = base64.b64encode(content).decode()
            return True, f"[二进制文件，base64]\n{b64}{suffix}", ""
    except FileNotFoundError:
        return False, "", f"文件不存在：{file_path}"
    except PermissionError:
        return False, "", f"权限不足：{file_path}"


@command("fs.write")
async def fs_write(params: dict) -> tuple[bool, str, str]:
    """写入文件。params: {path: str, content: str, mode?: "w"|"a"}"""
    file_path = Path(params.get("path", ""))
    content = params.get("content", "")
    mode = params.get("mode", "w")
    if mode not in ("w", "a"):
        return False, "", "mode 必须为 'w'（覆盖）或 'a'（追加）"
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, mode, encoding="utf-8") as f:
            f.write(content)
        return True, f"已写入：{file_path}（{len(content)} 字符）", ""
    except PermissionError:
        return False, "", f"权限不足：{file_path}"
    except Exception as e:
        return False, "", str(e)


# ─────────────────────────────────────────────────────────────────────────────
# 系统信息命令
# ─────────────────────────────────────────────────────────────────────────────

@command("sys.info")
async def sys_info(params: dict) -> tuple[bool, str, str]:
    """获取系统信息（CPU/内存/磁盘/网络）。"""
    lines = [
        f"系统：{platform.system()} {platform.release()} {platform.machine()}",
        f"节点名：{platform.node()}",
        f"Python：{sys.version.split()[0]}",
    ]

    try:
        import psutil  # type: ignore
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        lines += [
            f"CPU 使用率：{cpu:.1f}%",
            f"内存：{mem.used / 1024**3:.1f} GB / {mem.total / 1024**3:.1f} GB（{mem.percent:.1f}%）",
            f"磁盘(/)：{disk.used / 1024**3:.1f} GB / {disk.total / 1024**3:.1f} GB（{disk.percent:.1f}%）",
        ]
    except ImportError:
        lines.append("（psutil 未安装，无法获取 CPU/内存/磁盘详情）")

    return True, "\n".join(lines), ""


# ─────────────────────────────────────────────────────────────────────────────
# 截图命令
# ─────────────────────────────────────────────────────────────────────────────

@command("screenshot")
async def screenshot(params: dict) -> tuple[bool, str, str]:
    """
    截取屏幕截图，返回 base64 编码的 PNG。
    params: {monitor?: int}  # monitor=0 表示全部屏幕
    """
    try:
        import mss  # type: ignore
        import mss.tools

        monitor_idx = int(params.get("monitor", 0))
        with mss.mss() as sct:
            monitors = sct.monitors
            if monitor_idx >= len(monitors):
                monitor_idx = 0
            monitor = monitors[monitor_idx]
            img = sct.grab(monitor)
            import io
            from PIL import Image  # type: ignore
            pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            buf = io.BytesIO()
            pil.save(buf, format="PNG", optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode()
            return True, f"[screenshot:base64:png]\n{b64}", ""
    except ImportError as e:
        return False, "", f"截图依赖未安装（{e}），请 pip install mss Pillow"
    except Exception as e:
        return False, "", f"截图失败：{e}"
