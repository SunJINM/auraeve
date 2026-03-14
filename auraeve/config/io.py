from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from auraeve.observability import get_observability

from .defaults import DEFAULTS, SENSITIVE_KEYS
from .env_substitution import substitute_env
from .includes import resolve_includes
from .paths import (
    resolve_config_path,
)
from .schema import HOT_KEYS, normalize_config_object, validate_config_object
from .stores import write_text_atomic
from .types import ConfigSnapshot

DEFAULT_BACKUP_KEEP = 5

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


def _parse_json(raw: str) -> dict[str, Any]:
    payload = json.loads(_strip_json_comments(raw))
    if not isinstance(payload, dict):
        raise ValueError("config root must be an object")
    return payload


def _hash_raw(raw: str | None) -> str:
    payload = raw if raw is not None else ""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _stamp_meta(config: dict[str, Any]) -> dict[str, Any]:
    out = dict(config)
    meta_raw = out.get("META")
    if not isinstance(meta_raw, dict):
        meta_raw = {}
    meta = dict(meta_raw)
    meta["updatedAt"] = datetime.now(timezone.utc).isoformat()
    meta["schema"] = "auraeve-config-v1"
    out["META"] = meta
    return out


def _maintain_backups(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    keep_raw = os.environ.get("AURAEVE_CONFIG_BACKUP_KEEP", "").strip()
    keep = DEFAULT_BACKUP_KEEP
    if keep_raw:
        try:
            keep = max(0, int(keep_raw))
        except Exception:
            keep = DEFAULT_BACKUP_KEEP
    if keep == 0:
        return
    try:
        legacy = path.with_suffix(path.suffix + ".bak")
        if legacy.exists() and legacy.is_file():
            legacy_slot = path.with_suffix(path.suffix + ".bak.1")
            if legacy_slot.exists():
                legacy_slot.unlink(missing_ok=True)
            legacy.replace(legacy_slot)

        for idx in range(keep, 1, -1):
            src = path.with_suffix(path.suffix + f".bak.{idx - 1}")
            dst = path.with_suffix(path.suffix + f".bak.{idx}")
            if src.exists():
                if dst.exists():
                    dst.unlink(missing_ok=True)
                src.replace(dst)

        newest = path.with_suffix(path.suffix + ".bak.1")
        shutil.copy2(path, newest)
    except Exception:
        return


def _append_config_audit(record: dict[str, Any]) -> None:
    event = dict(record)
    result = str(event.get("result") or "unknown")
    action = str(event.get("event") or "config.write")
    get_observability().emit_audit(
        subsystem="config",
        action=action,
        attrs={
            "result": result,
            "record": event,
        },
    )


def read_config_snapshot() -> ConfigSnapshot:
    path = resolve_config_path()
    exists = path.exists()
    if not exists:
        config = normalize_config_object({})
        return ConfigSnapshot(
            path=path,
            exists=False,
            raw=None,
            parsed={},
            resolved={},
            config=config,
            valid=True,
            issues=[],
            warnings=[],
            base_hash=_hash_raw(None),
        )

    raw = path.read_text(encoding="utf-8")
    warnings: list[dict[str, str]] = []
    try:
        parsed = _parse_json(raw)
        resolved_includes = resolve_includes(parsed, path, path.parent)
        resolved = substitute_env(resolved_includes, warnings)
        if not isinstance(resolved, dict):
            raise ValueError("resolved config must be object")
        valid, issues = validate_config_object(resolved)
        config = normalize_config_object(resolved if valid else {})
        return ConfigSnapshot(
            path=path,
            exists=True,
            raw=raw,
            parsed=parsed,
            resolved=resolved,
            config=config,
            valid=valid,
            issues=issues,
            warnings=warnings,
            base_hash=_hash_raw(raw),
        )
    except Exception as exc:
        return ConfigSnapshot(
            path=path,
            exists=True,
            raw=raw,
            parsed={},
            resolved={},
            config=normalize_config_object({}),
            valid=False,
            issues=[{"path": "<root>", "message": str(exc)}],
            warnings=warnings,
            base_hash=_hash_raw(raw),
        )


def load_config() -> dict[str, Any]:
    snapshot = read_config_snapshot()
    if snapshot.valid:
        return dict(snapshot.config)
    return dict(DEFAULTS)


def _restore_sensitive_refs(
    output: dict[str, Any],
    previous_parsed: dict[str, Any],
    changed_keys: set[str],
) -> dict[str, Any]:
    restored = dict(output)
    for key in SENSITIVE_KEYS:
        if key in changed_keys:
            continue
        previous = previous_parsed.get(key)
        if isinstance(previous, str) and "${" in previous:
            restored[key] = previous
    return restored


def write_config(
    new_config: dict[str, Any],
    *,
    base_hash: str | None = None,
    unset_keys: list[str] | None = None,
) -> tuple[bool, ConfigSnapshot, list[str], list[str], list[dict[str, str]]]:
    started_at = datetime.now(timezone.utc).isoformat()
    snapshot = read_config_snapshot()
    if base_hash is not None and base_hash != snapshot.base_hash:
        _append_config_audit(
            {
                "ts": started_at,
                "event": "config.write",
                "result": "hash_conflict",
                "path": str(snapshot.path),
                "baseHash": snapshot.base_hash,
            }
        )
        return (
            False,
            snapshot,
            [],
            [],
            [{"path": "<root>", "message": "hash conflict, reload latest config first"}],
        )

    candidate = dict(snapshot.resolved if snapshot.valid else {})
    for key, value in new_config.items():
        candidate[key] = value
    if unset_keys:
        for key in unset_keys:
            candidate.pop(key, None)

    valid, issues = validate_config_object(candidate)
    if not valid:
        _append_config_audit(
            {
                "ts": started_at,
                "event": "config.write",
                "result": "validation_failed",
                "path": str(snapshot.path),
                "baseHash": snapshot.base_hash,
                "issues": issues[:20],
            }
        )
        return (False, snapshot, [], [], issues)

    normalized = normalize_config_object(candidate)
    changed = sorted(
        key for key in normalized.keys() if normalized.get(key) != snapshot.config.get(key)
    )
    output = _stamp_meta(normalized)
    output = _restore_sensitive_refs(output, snapshot.parsed, set(changed))

    raw = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    path = resolve_config_path()
    _maintain_backups(path)
    write_text_atomic(path, raw)
    next_snapshot = read_config_snapshot()
    requires_restart = [
        key
        for key in changed
        if key not in HOT_KEYS
    ]
    _append_config_audit(
        {
            "ts": started_at,
            "event": "config.write",
            "result": "ok",
            "path": str(path),
            "baseHashBefore": snapshot.base_hash,
            "baseHashAfter": next_snapshot.base_hash,
            "changed": changed,
            "requiresRestart": requires_restart,
        }
    )
    return (True, next_snapshot, changed, requires_restart, [])
