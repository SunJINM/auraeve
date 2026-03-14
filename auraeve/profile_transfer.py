from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import auraeve.config as cfg

ARCHIVE_FORMAT = "auraeve-profile-v1"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _iter_files(base: Path) -> list[Path]:
    if not base.exists():
        return []
    out: list[Path] = []
    for p in sorted(base.rglob("*")):
        if p.is_symlink() or not p.is_file():
            continue
        out.append(p)
    return out


def export_profile_archive(output_path: str | Path) -> dict[str, Any]:
    state_dir = cfg.resolve_state_dir().resolve()
    config_path = cfg.resolve_config_path().resolve()

    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    state_files = _iter_files(state_dir)
    config_embedded_in_state = _is_within(config_path, state_dir)
    include_external_config = config_path.exists() and not config_embedded_in_state

    total_files = 0
    total_bytes = 0

    with zipfile.ZipFile(target, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for file_path in state_files:
            if file_path == target:
                continue
            rel = file_path.relative_to(state_dir).as_posix()
            arcname = f"state/{rel}"
            zf.write(file_path, arcname=arcname)
            total_files += 1
            total_bytes += file_path.stat().st_size

        if include_external_config:
            arc_cfg = "external/config/auraeve.json"
            zf.write(config_path, arcname=arc_cfg)
            total_files += 1
            total_bytes += config_path.stat().st_size

        manifest = {
            "format": ARCHIVE_FORMAT,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "source": {
                "stateDir": str(state_dir),
                "configPath": str(config_path),
                "configEmbeddedInState": config_embedded_in_state,
            },
            "stats": {
                "files": total_files,
                "bytes": total_bytes,
            },
        }
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    return {
        "ok": True,
        "archive": str(target),
        "files": total_files,
        "bytes": total_bytes,
        "stateDir": str(state_dir),
        "configPath": str(config_path),
        "format": ARCHIVE_FORMAT,
    }


def _validate_archive_member(name: str) -> None:
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"unsafe archive member path: {name}")


def import_profile_archive(archive_path: str | Path, *, force: bool = False) -> dict[str, Any]:
    archive = Path(archive_path).expanduser().resolve()
    if not archive.exists() or not archive.is_file():
        raise FileNotFoundError(f"archive not found: {archive}")

    state_dir = cfg.resolve_state_dir().resolve()
    config_path = cfg.resolve_config_path().resolve()

    if state_dir.exists() and any(state_dir.iterdir()) and not force:
        raise RuntimeError("target state directory is not empty; re-run with --force to overwrite")

    with tempfile.TemporaryDirectory(prefix="auraeve-import-") as tmp:
        temp_root = Path(tmp)
        temp_state = temp_root / "state"
        temp_external_cfg = temp_root / "external" / "config" / "auraeve.json"
        manifest: dict[str, Any] | None = None

        with zipfile.ZipFile(archive, mode="r") as zf:
            names = zf.namelist()
            if "manifest.json" not in names:
                raise RuntimeError("invalid archive: missing manifest.json")
            for name in names:
                _validate_archive_member(name)
                if name.endswith("/"):
                    continue
                dst = temp_root / PurePosixPath(name)
                dst.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name, "r") as src, dst.open("wb") as out:
                    out.write(src.read())
            manifest = json.loads((temp_root / "manifest.json").read_text(encoding="utf-8"))

        if not isinstance(manifest, dict) or manifest.get("format") != ARCHIVE_FORMAT:
            raise RuntimeError("invalid archive format")

        backup_state: Path | None = None
        backup_config: Path | None = None
        stamp = _utc_stamp()

        if force and state_dir.exists():
            backup_state = state_dir.parent / f"{state_dir.name}.backup-{stamp}"
            if backup_state.exists():
                shutil.rmtree(backup_state, ignore_errors=True)
            state_dir.rename(backup_state)

        try:
            if state_dir.exists():
                shutil.rmtree(state_dir, ignore_errors=True)

            if temp_state.exists():
                shutil.copytree(temp_state, state_dir)
            else:
                state_dir.mkdir(parents=True, exist_ok=True)

            restored_external_config = False
            if temp_external_cfg.exists() and not _is_within(config_path, state_dir):
                config_path.parent.mkdir(parents=True, exist_ok=True)
                if force and config_path.exists():
                    backup_config = config_path.parent / f"{config_path.name}.backup-{stamp}"
                    shutil.copy2(config_path, backup_config)
                shutil.copy2(temp_external_cfg, config_path)
                restored_external_config = True

        except Exception:
            if state_dir.exists():
                shutil.rmtree(state_dir, ignore_errors=True)
            if backup_state and backup_state.exists():
                backup_state.rename(state_dir)
            raise

    return {
        "ok": True,
        "archive": str(archive),
        "stateDir": str(state_dir),
        "configPath": str(config_path),
        "stateBackup": str(backup_state) if backup_state else "",
        "configBackup": str(backup_config) if backup_config else "",
        "format": ARCHIVE_FORMAT,
    }
