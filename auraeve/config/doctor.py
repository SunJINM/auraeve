from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .defaults import DEFAULTS
from .legacy import migrate_legacy_config_object
from .io import read_config_snapshot, write_config
from .paths import resolve_config_path


def _strip_json_comments(raw: str) -> str:
    out: list[str] = []
    i = 0
    in_string = False
    in_line_comment = False
    in_block_comment = False
    while i < len(raw):
        ch = raw[i]
        nxt = raw[i + 1] if i + 1 < len(raw) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_string:
            out.append(ch)
            if ch == "\\":
                if i + 1 < len(raw):
                    out.append(raw[i + 1])
                    i += 2
                    continue
            elif ch == "\"":
                in_string = False
            i += 1
            continue
        if ch == "\"":
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _load_raw_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return {}
    try:
        payload = json.loads(_strip_json_comments(path.read_text(encoding="utf-8")))
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
        migration_notes: list[str] = []
        migrated_obj = raw_obj
        legacy_needs_rewrite = False
        if isinstance(raw_obj, dict):
            migrated_obj, migration_notes = migrate_legacy_config_object(raw_obj)
            legacy_needs_rewrite = migrated_obj != raw_obj

        if snapshot.valid and not (fix and legacy_needs_rewrite):
            return {
                "ok": True,
                "fixed": False,
                "path": str(snapshot.path),
                "issues": [],
                "warnings": [*snapshot.warnings, *({"path": "legacy", "message": n} for n in migration_notes)],
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
        cleaned = {k: v for k, v in (migrated_obj or {}).items() if k in allowed}
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
            "warnings": [*next_snapshot.warnings, *({"path": "MCP", "message": n} for n in migration_notes)],
            "changed": changed,
            "requiresRestart": requires_restart,
        }
    finally:
        from auraeve.observability.manager import close_observability

        close_observability()
