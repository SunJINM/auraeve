from __future__ import annotations

import hashlib
import shutil
import tarfile
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from auraeve.config.paths import resolve_state_dir

from .manifest import parse_skill_entry
from .state import load_skills_state, resolve_managed_skills_dir, save_skills_state


MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_UPLOAD_SUFFIXES = (".zip", ".tar.gz", ".tgz")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_upload_suffix(filename: str) -> str:
    name = (filename or "").strip().lower()
    if name.endswith(".tar.gz"):
        return ".tar.gz"
    if name.endswith(".tgz"):
        return ".tgz"
    if name.endswith(".zip"):
        return ".zip"
    return ""


def _sanitize_file_component(raw: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in raw)
    return safe.strip("._") or "file"


def resolve_upload_tmp_dir() -> Path:
    return resolve_state_dir() / "skills" / "uploads" / "tmp"


def resolve_upload_staging_root() -> Path:
    return resolve_state_dir() / "skills" / "uploads" / "staging"


def save_uploaded_archive_bytes(filename: str, payload: bytes) -> dict[str, Any]:
    suffix = _normalize_upload_suffix(filename)
    if not suffix:
        return {"ok": False, "message": "unsupported archive type; allowed: .zip/.tar.gz/.tgz"}
    if len(payload) > MAX_UPLOAD_BYTES:
        return {"ok": False, "message": f"file too large; max {MAX_UPLOAD_BYTES} bytes"}

    upload_id = uuid.uuid4().hex
    tmp_dir = resolve_upload_tmp_dir()
    tmp_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _sanitize_file_component(Path(filename).name)
    target = tmp_dir / f"{upload_id}-{safe_name}"
    target.write_bytes(payload)

    digest = hashlib.sha256(payload).hexdigest()

    state = load_skills_state()
    uploads = state.setdefault("uploads", {})
    if not isinstance(uploads, dict):
        uploads = {}
        state["uploads"] = uploads
    uploads[upload_id] = {
        "filename": filename,
        "size": len(payload),
        "sha256": digest,
        "path": str(target),
        "createdAt": _now_iso(),
        "consumedAt": None,
    }
    save_skills_state(state)
    return {
        "ok": True,
        "uploadId": upload_id,
        "filename": filename,
        "size": len(payload),
        "sha256": digest,
        "message": "upload accepted",
    }


def _safe_extract_zip(source: Path, dest: Path) -> None:
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(source, "r") as zf:
        for member in zf.infolist():
            member_name = member.filename
            if not member_name:
                continue
            target = (dest / member_name).resolve()
            if target != dest_resolved and dest_resolved not in target.parents:
                raise ValueError(f"unsafe archive path: {member_name}")
        zf.extractall(dest)


def _safe_extract_tar(source: Path, dest: Path) -> None:
    dest_resolved = dest.resolve()
    with tarfile.open(source, "r:*") as tf:
        for member in tf.getmembers():
            member_name = member.name
            if not member_name:
                continue
            target = (dest / member_name).resolve()
            if target != dest_resolved and dest_resolved not in target.parents:
                raise ValueError(f"unsafe archive path: {member_name}")
        tf.extractall(dest)


def extract_archive_safe(source: Path, staging_dir: Path) -> Path:
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    if zipfile.is_zipfile(source):
        _safe_extract_zip(source, staging_dir)
        return staging_dir

    if source.name.lower().endswith(".tar.gz") or source.name.lower().endswith(".tgz"):
        _safe_extract_tar(source, staging_dir)
        return staging_dir

    raise ValueError(f"unsupported archive: {source}")


def discover_skills_in_staging(staging_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for skill_file in staging_dir.rglob("SKILL.md"):
        if not skill_file.is_file():
            continue
        skill_dir = skill_file.parent.resolve()
        key = str(skill_dir)
        if key in seen:
            continue
        seen.add(key)
        parsed = parse_skill_entry(skill_dir, "managed")
        if parsed is None:
            continue
        skill_key = parsed.metadata.skill_key or parsed.name
        out.append(
            {
                "name": parsed.name,
                "skillKey": skill_key,
                "baseDir": skill_dir,
            }
        )
    out.sort(key=lambda x: (x["name"], x["skillKey"]))
    return out


def _normalize_target_dir_name(name_or_key: str) -> str:
    raw = (name_or_key or "").strip()
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in raw)
    safe = safe.strip("-_")
    return safe or "skill"


def _state_upload(upload_id: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    state = load_skills_state()
    uploads = state.get("uploads") if isinstance(state.get("uploads"), dict) else {}
    if not isinstance(uploads, dict):
        return state, None
    item = uploads.get(upload_id)
    if not isinstance(item, dict):
        return state, None
    return state, item


def install_skills_from_uploaded_archive(upload_id: str, *, force: bool = False) -> dict[str, Any]:
    state, upload_item = _state_upload(upload_id)
    if upload_item is None:
        return {"ok": False, "message": f"upload not found: {upload_id}"}
    archive_path = Path(str(upload_item.get("path", ""))).expanduser().resolve()
    if not archive_path.exists() or not archive_path.is_file():
        return {"ok": False, "message": "uploaded archive file not found"}

    staging_root = resolve_upload_staging_root()
    staging_dir = staging_root / upload_id
    managed_root = resolve_managed_skills_dir()
    managed_root.mkdir(parents=True, exist_ok=True)

    installed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    installs = state.setdefault("installs", {})
    if not isinstance(installs, dict):
        installs = {}
        state["installs"] = installs

    try:
        extract_archive_safe(archive_path, staging_dir)
        candidates = discover_skills_in_staging(staging_dir)
        if not candidates:
            return {"ok": False, "message": "no valid SKILL.md found in archive"}

        for item in candidates:
            source_dir = Path(item["baseDir"])
            skill_name = str(item["name"])
            skill_key = str(item["skillKey"])
            target_name = _normalize_target_dir_name(skill_key or skill_name)
            target = (managed_root / target_name).resolve()
            if target.exists():
                if not force:
                    skipped.append({"name": skill_name, "skillKey": skill_key, "reason": "already exists"})
                    continue
                shutil.rmtree(target, ignore_errors=True)
            try:
                shutil.copytree(source_dir, target)
                installed.append(
                    {
                        "name": skill_name,
                        "skillKey": skill_key,
                        "installPath": str(target),
                        "source": "upload_archive",
                    }
                )
                installs[skill_key] = {
                    "skill": skill_name,
                    "skillKey": skill_key,
                    "sourceType": "upload_archive",
                    "sourceRef": upload_id,
                    "archiveSha256": upload_item.get("sha256"),
                    "installPath": str(target),
                    "installedAt": _now_iso(),
                }
            except Exception as exc:
                failed.append({"entry": skill_name, "reason": str(exc)})

        uploads = state.get("uploads") if isinstance(state.get("uploads"), dict) else {}
        if isinstance(uploads, dict) and upload_id in uploads and isinstance(uploads[upload_id], dict):
            uploads[upload_id]["consumedAt"] = _now_iso()
        save_skills_state(state)

        ok = bool(installed) and not failed
        if not installed and (failed or skipped):
            ok = False
        return {
            "ok": ok,
            "message": (
                f"installed {len(installed)} skill(s), skipped {len(skipped)}, failed {len(failed)}"
            ),
            "installed": installed,
            "skipped": skipped,
            "failed": failed,
        }
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)
        if archive_path.exists():
            archive_path.unlink(missing_ok=True)


def build_malicious_archive_for_test(target_file: Path) -> None:
    """Helper for tests only: create a zip containing path traversal entry."""
    tmp = Path(tempfile.mkdtemp(prefix="auraeve-skill-test-"))
    try:
        inner = tmp / "safe.txt"
        inner.write_text("ok", encoding="utf-8")
        with zipfile.ZipFile(target_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(inner, arcname="../evil.txt")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
