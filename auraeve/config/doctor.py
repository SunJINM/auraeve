from __future__ import annotations

import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .defaults import DEFAULTS
from .io import read_config_snapshot, write_config
from .paths import resolve_config_path


def _load_raw_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return {}
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def run_config_doctor(*, fix: bool = False) -> dict[str, Any]:
    try:
        snapshot = read_config_snapshot()
        path = resolve_config_path()
        raw_obj = _load_raw_object(path)

        if snapshot.valid:
            return {
                "ok": True,
                "fixed": False,
                "path": str(snapshot.path),
                "issues": [],
                "warnings": snapshot.warnings,
            }

        issues = [*snapshot.issues]
        warnings = [*snapshot.warnings]
        if not fix:
            return {
                "ok": False,
                "fixed": False,
                "path": str(snapshot.path),
                "issues": issues,
                "warnings": warnings,
            }

        if raw_obj is None:
            # cannot parse, preserve a corrupt copy then reset to defaults
            if path.exists():
                corrupt = path.with_suffix(path.suffix + f".corrupt-{int(datetime.now(timezone.utc).timestamp())}")
                path.replace(corrupt)
            ok, next_snapshot, changed, requires_restart, write_issues = write_config(dict(DEFAULTS))
            return {
                "ok": bool(ok),
                "fixed": bool(ok),
                "path": str(next_snapshot.path),
                "issues": write_issues,
                "warnings": next_snapshot.warnings,
                "changed": changed,
                "requiresRestart": requires_restart,
            }

        # prune unknown keys; keep META if present
        allowed = set(DEFAULTS.keys()) | {"META"}
        cleaned = {k: v for k, v in (raw_obj or {}).items() if k in allowed}
        # remove known bad types by falling back to default value
        for issue in issues:
            path_key = issue.get("path", "")
            if path_key in DEFAULTS:
                cleaned[path_key] = DEFAULTS[path_key]

        ok, next_snapshot, changed, requires_restart, write_issues = write_config(cleaned)
        return {
            "ok": bool(ok),
            "fixed": bool(ok),
            "path": str(next_snapshot.path),
            "issues": write_issues,
            "warnings": next_snapshot.warnings,
            "changed": changed,
            "requiresRestart": requires_restart,
        }
    finally:
        from auraeve.observability.manager import close_observability

        close_observability()
