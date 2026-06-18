from __future__ import annotations

import hashlib
import os
import re
import shutil
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .defaults import DEFAULTS, SENSITIVE_KEYS
from .env_substitution import substitute_env
from .paths import (
    resolve_config_path,
)
from .schema import HOT_KEYS, normalize_config_object, validate_config_object
from .stores import write_text_atomic
from .types import ConfigSnapshot

DEFAULT_BACKUP_KEEP = 5

def _parse_toml(raw: str) -> dict[str, Any]:
    payload = tomllib.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("config root must be an object")
    return payload


def _toml_key(key: str) -> str:
    if key.replace("_", "").replace("-", "").isalnum():
        return key
    escaped = key.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\b", "\\b")
        .replace("\f", "\\f")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return _toml_string(value)
    raise TypeError(f"unsupported TOML scalar: {type(value).__name__}")


def _is_scalar(value: Any) -> bool:
    return isinstance(value, bool | int | float | str)


def _toml_inline_value(value: Any) -> str:
    if value is None:
        raise TypeError("TOML does not support null")
    if _is_scalar(value):
        return _toml_scalar(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_inline_value(item) for item in value if item is not None) + "]"
    if isinstance(value, dict):
        parts = [
            f"{_toml_key(str(key))} = {_toml_inline_value(item)}"
            for key, item in value.items()
            if item is not None
        ]
        return "{ " + ", ".join(parts) + " }"
    raise TypeError(f"unsupported TOML value: {type(value).__name__}")


def _toml_assignment(key: str, value: Any) -> str:
    return f"{_toml_key(key)} = {_toml_inline_value(value)}"


def _emit_toml_table(lines: list[str], table: dict[str, Any], prefix: list[str]) -> None:
    simple_items: list[tuple[str, Any]] = []
    dict_items: list[tuple[str, dict[str, Any]]] = []
    list_dict_items: list[tuple[str, list[dict[str, Any]]]] = []

    for raw_key, value in table.items():
        key = str(raw_key)
        if value is None:
            continue
        if isinstance(value, dict):
            dict_items.append((key, value))
        elif isinstance(value, list) and any(isinstance(item, dict) for item in value):
            if not all(isinstance(item, dict) for item in value):
                raise TypeError(f"TOML array '{'.'.join([*prefix, key])}' cannot mix objects and scalars")
            list_dict_items.append((key, value))
        else:
            simple_items.append((key, value))

    for key, value in simple_items:
        lines.append(_toml_assignment(key, value))

    for key, value in dict_items:
        if lines and lines[-1] != "":
            lines.append("")
        section = ".".join(_toml_key(part) for part in [*prefix, key])
        lines.append(f"[{section}]")
        _emit_toml_table(lines, value, [*prefix, key])

    for key, items in list_dict_items:
        for item in items:
            if lines and lines[-1] != "":
                lines.append("")
            section = ".".join(_toml_key(part) for part in [*prefix, key])
            lines.append(f"[[{section}]]")
            _emit_toml_table(lines, item, [*prefix, key])


def _to_toml(config: dict[str, Any]) -> str:
    lines: list[str] = []
    _emit_toml_table(lines, config, [])
    return "\n".join(lines).rstrip() + "\n"


def _replace_first_assignment(text: str, key: str, value: Any) -> tuple[str, bool]:
    if value is None or isinstance(value, dict | list):
        return text, False
    pattern = re.compile(rf"(?m)^({re.escape(key)}\s*=\s*)[^\r\n]*$")
    next_text, count = pattern.subn(lambda match: match.group(1) + _toml_inline_value(value), text, count=1)
    return next_text, count > 0


def _replace_section_assignment(text: str, section: str, key: str, value: Any) -> tuple[str, bool]:
    if value is None or isinstance(value, dict | list):
        return text, False
    pattern = re.compile(
        rf"(?ms)^(\[{re.escape(section)}\]\s*\n.*?^){re.escape(key)}\s*=\s*[^\r\n]*$"
    )
    next_text, count = pattern.subn(
        lambda match: match.group(1) + f"{key} = {_toml_inline_value(value)}",
        text,
        count=1,
    )
    return next_text, count > 0


def _replace_first_array_table_assignment(text: str, table: str, key: str, value: Any) -> tuple[str, bool]:
    if value is None or isinstance(value, dict | list):
        return text, False
    pattern = re.compile(
        rf"(?ms)^(\[\[{re.escape(table)}\]\]\s*\n.*?^){re.escape(key)}\s*=\s*[^\r\n]*$"
    )
    next_text, count = pattern.subn(
        lambda match: match.group(1) + f"{key} = {_toml_inline_value(value)}",
        text,
        count=1,
    )
    return next_text, count > 0


def _remove_empty_template_entry(text: str, key: str) -> str:
    text = re.sub(rf"(?ms)^# 配置项：{re.escape(key)}\n.*?^{re.escape(key)}\s*=\s*(?:\{{\}}|\[\])\n", "", text, count=1)
    text = re.sub(rf"(?m)^\[{re.escape(key)}\]\n(?:\n)?", "", text, count=1)
    return text


def _to_commented_toml(config: dict[str, Any]) -> str:
    template_path = Path(__file__).resolve().parents[1] / "config.example.toml"
    try:
        text = template_path.read_text(encoding="utf-8")
    except Exception:
        return _to_toml(config)

    replaced: set[str] = set()
    for key, value in config.items():
        next_text, ok = _replace_first_assignment(text, key, value)
        if ok:
            text = next_text
            replaced.add(key)

    first_model = (config.get("LLM_MODELS") or [{}])[0]
    if isinstance(first_model, dict):
        for key, value in first_model.items():
            if key in {"extraHeaders", "capabilities"}:
                continue
            text, _ok = _replace_first_array_table_assignment(text, "LLM_MODELS", key, value)
        capabilities = first_model.get("capabilities")
        if isinstance(capabilities, dict):
            for key, value in capabilities.items():
                text, _ok = _replace_section_assignment(text, "LLM_MODELS.capabilities", key, value)

    for section in ("READ_ROUTING", "RUNTIME_LOOP_GUARD", "ASR", "MCP", "LOGGING"):
        table = config.get(section)
        if not isinstance(table, dict):
            continue
        replaced.add(section)
        for key, value in table.items():
            text, _ok = _replace_section_assignment(text, section, key, value)

    logging = config.get("LOGGING")
    if isinstance(logging, dict):
        stream = logging.get("stream")
        if isinstance(stream, dict):
            for key, value in stream.items():
                text, _ok = _replace_section_assignment(text, "LOGGING.stream", key, value)
        search = logging.get("search")
        if isinstance(search, dict):
            for key, value in search.items():
                text, _ok = _replace_section_assignment(text, "LOGGING.search", key, value)

    empty_template_keys = {
        "AGENTS_DEFAULTS",
        "AGENTS_LIST",
        "SKILLS_ENTRIES",
        "SESSION_TOOL_POLICY",
        "CHANNEL_USERS",
    }
    missing = {
        key: value
        for key, value in config.items()
        if key not in replaced and key not in {"LLM_MODELS"}
    }
    for key in empty_template_keys:
        value = config.get(key)
        if value in ({}, []):
            missing.pop(key, None)
        elif key in missing:
            text = _remove_empty_template_entry(text, key)
    if missing:
        text = text.rstrip() + "\n\n# ============================================================\n"
        text += "# 自动追加配置\n"
        text += "# 作用：保存当前版本支持但注释模板尚未显式展示的配置项。\n"
        text += "# ============================================================\n\n"
        text += _to_toml(missing).rstrip() + "\n"

    return text.rstrip() + "\n"


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
    from auraeve.observability.manager import get_observability

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
        parsed = _parse_toml(raw)
        resolved = substitute_env(parsed, warnings)
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

    raw = _to_commented_toml(output)
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
