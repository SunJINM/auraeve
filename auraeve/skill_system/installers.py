from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import SkillEntry, SkillInstallResult, SkillInstallSpec, SkillsInstallPreferences
from .state import resolve_tools_dir


def _decode_output(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    for enc in ("utf-8", "gbk", "cp936"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def _run(argv: list[str], timeout_ms: int, env: dict[str, str] | None = None) -> SkillInstallResult:
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=False,
            timeout=max(1, timeout_ms) / 1000,
            env={**os.environ, **(env or {})},
            check=False,
        )
        return SkillInstallResult(
            ok=completed.returncode == 0,
            message="Installed" if completed.returncode == 0 else f"Install failed (exit {completed.returncode})",
            code=completed.returncode,
            stdout=_decode_output(completed.stdout).strip(),
            stderr=_decode_output(completed.stderr).strip(),
        )
    except Exception as exc:
        return SkillInstallResult(ok=False, message=str(exc), code=None, stdout="", stderr=str(exc))


def _safe_skill_tools_root(entry: SkillEntry) -> Path:
    key = entry.metadata.skill_key or entry.name
    hashed = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    root = resolve_tools_dir() / f"{key.replace('/', '_')}-{hashed}"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _safe_target_dir(entry: SkillEntry, spec: SkillInstallSpec) -> Path:
    root = _safe_skill_tools_root(entry)
    if not spec.target_dir:
        return root
    raw = spec.target_dir.strip()
    if raw.startswith("~"):
        candidate = Path(os.path.expanduser(raw)).resolve()
    else:
        candidate = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
    if not str(candidate).startswith(str(root)):
        raise ValueError(f"targetDir escapes tools root: {candidate}")
    return candidate


def _safe_extract_tar(archive_path: Path, target_dir: Path, strip_components: int = 0) -> None:
    with tarfile.open(archive_path, "r:*") as tf:
        for member in tf.getmembers():
            name = member.name
            parts = [p for p in Path(name).parts if p not in {"", "."}]
            if strip_components > 0:
                parts = parts[strip_components:]
            if not parts:
                continue
            rel = Path(*parts)
            if any(p == ".." for p in rel.parts):
                raise ValueError(f"unsafe archive path: {name}")
            dest = (target_dir / rel).resolve()
            if not str(dest).startswith(str(target_dir.resolve())):
                raise ValueError(f"unsafe archive path: {name}")
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            if member.issym() or member.islnk():
                raise ValueError("symlink/hardlink entries are not allowed")
            dest.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                continue
            with src, dest.open("wb") as f:
                shutil.copyfileobj(src, f)


def _safe_extract_zip(archive_path: Path, target_dir: Path, strip_components: int = 0) -> None:
    with zipfile.ZipFile(archive_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename
            parts = [p for p in Path(name).parts if p not in {"", "."}]
            if strip_components > 0:
                parts = parts[strip_components:]
            if not parts:
                continue
            rel = Path(*parts)
            if any(p == ".." for p in rel.parts):
                raise ValueError(f"unsafe archive path: {name}")
            dest = (target_dir / rel).resolve()
            if not str(dest).startswith(str(target_dir.resolve())):
                raise ValueError(f"unsafe archive path: {name}")
            if info.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, dest.open("wb") as f:
                shutil.copyfileobj(src, f)


def _install_download(
    entry: SkillEntry,
    spec: SkillInstallSpec,
    prefs: SkillsInstallPreferences,
) -> SkillInstallResult:
    if not spec.url:
        return SkillInstallResult(ok=False, message="missing download url")

    parsed = urllib.parse.urlparse(spec.url)
    if parsed.scheme not in {"http", "https"}:
        return SkillInstallResult(ok=False, message="unsupported download scheme")

    allowed = set(prefs.allow_download_domains)
    if allowed and parsed.hostname and parsed.hostname not in allowed:
        return SkillInstallResult(ok=False, message=f"download domain not allowed: {parsed.hostname}")

    target_dir = _safe_target_dir(entry, spec)
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = Path(parsed.path).name or "download.bin"
    archive_path = (target_dir / filename).resolve()

    try:
        with urllib.request.urlopen(spec.url, timeout=max(1, prefs.timeout_ms) / 1000) as resp:
            data = resp.read()
        archive_path.write_bytes(data)
    except Exception as exc:
        return SkillInstallResult(ok=False, message=f"download failed: {exc}", stderr=str(exc))

    should_extract = spec.extract if spec.extract is not None else archive_path.suffix.lower() in {
        ".zip",
        ".gz",
        ".tgz",
        ".bz2",
        ".xz",
        ".tar",
    }
    if not should_extract:
        return SkillInstallResult(ok=True, message=f"Downloaded to {archive_path}", code=0)

    strip_components = spec.strip_components or 0
    try:
        lower_name = archive_path.name.lower()
        if lower_name.endswith(".zip"):
            _safe_extract_zip(archive_path, target_dir, strip_components=strip_components)
        else:
            _safe_extract_tar(archive_path, target_dir, strip_components=strip_components)
    except Exception as exc:
        return SkillInstallResult(ok=False, message=f"extract failed: {exc}", stderr=str(exc))

    return SkillInstallResult(ok=True, message=f"Downloaded and extracted to {target_dir}", code=0)


def install_spec(entry: SkillEntry, spec: SkillInstallSpec, prefs: SkillsInstallPreferences) -> SkillInstallResult:
    timeout = prefs.timeout_ms
    if spec.kind == "brew":
        if not spec.formula:
            return SkillInstallResult(ok=False, message="missing brew formula")
        if not shutil.which("brew"):
            return SkillInstallResult(ok=False, message="required installer command not found: brew")
        return _run(["brew", "install", spec.formula], timeout)

    if spec.kind == "apt":
        if not spec.package:
            return SkillInstallResult(ok=False, message="missing apt package")
        if not shutil.which("apt-get"):
            return SkillInstallResult(ok=False, message="required installer command not found: apt-get")
        cmd = ["apt-get", "install", "-y", spec.package]
        if os.name != "nt" and hasattr(os, "getuid") and os.getuid() != 0 and shutil.which("sudo"):
            cmd = ["sudo", "-n", *cmd]
        return _run(cmd, timeout)

    if spec.kind == "node":
        if not spec.package:
            return SkillInstallResult(ok=False, message="missing node package")
        manager = prefs.node_manager
        if manager == "pnpm":
            if not shutil.which("pnpm"):
                return SkillInstallResult(ok=False, message="required installer command not found: pnpm")
            return _run(["pnpm", "add", "-g", "--ignore-scripts", spec.package], timeout)
        if manager == "yarn":
            if not shutil.which("yarn"):
                return SkillInstallResult(ok=False, message="required installer command not found: yarn")
            return _run(["yarn", "global", "add", "--ignore-scripts", spec.package], timeout)
        if manager == "bun":
            if not shutil.which("bun"):
                return SkillInstallResult(ok=False, message="required installer command not found: bun")
            return _run(["bun", "add", "-g", "--ignore-scripts", spec.package], timeout)
        if not shutil.which("npm"):
            return SkillInstallResult(ok=False, message="required installer command not found: npm")
        return _run(["npm", "install", "-g", "--ignore-scripts", spec.package], timeout)

    if spec.kind == "go":
        if not spec.module:
            return SkillInstallResult(ok=False, message="missing go module")
        if not shutil.which("go"):
            return SkillInstallResult(ok=False, message="required installer command not found: go")
        return _run(["go", "install", spec.module], timeout)

    if spec.kind == "uv":
        if not spec.package:
            return SkillInstallResult(ok=False, message="missing uv package")
        if not shutil.which("uv"):
            return SkillInstallResult(ok=False, message="required installer command not found: uv")
        return _run(["uv", "tool", "install", spec.package], timeout)

    if spec.kind == "download":
        return _install_download(entry, spec, prefs)

    return SkillInstallResult(ok=False, message=f"unsupported installer kind: {spec.kind}")


def serialize_install_spec(spec: SkillInstallSpec) -> dict[str, Any]:
    return asdict(spec)
