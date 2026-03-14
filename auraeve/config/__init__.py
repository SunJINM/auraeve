from __future__ import annotations

from pathlib import Path
from typing import Any

from .defaults import DEFAULTS, PATH_KEYS, SENSITIVE_KEYS
from .doctor import run_config_doctor
from .io import (
    ConfigSnapshot,
    load_config as _load_config,
    read_config_snapshot,
    write_config,
)
from .paths import (
    explain_workspace_resolution,
    resolve_agent_workspace_dir,
    resolve_agents_dir,
    resolve_agent_dir,
    resolve_config_path,
    resolve_cron_store_path,
    resolve_default_workspace_dir,
    resolve_nodes_dir,
    resolve_sessions_dir,
    resolve_state_dir,
    resolve_vector_db_path,
)

_RUNTIME_CONFIG: dict[str, Any] = {}


def _coerce_runtime_value(key: str, value: Any) -> Any:
    if key in PATH_KEYS and isinstance(value, str):
        p = Path(value).expanduser()
        if p.is_absolute():
            return p
        config_dir = resolve_config_path().parent
        return (config_dir / p).resolve()
    return value


def reload() -> dict[str, Any]:
    global _RUNTIME_CONFIG
    loaded = _load_config()
    _RUNTIME_CONFIG = dict(loaded)
    for key, value in _RUNTIME_CONFIG.items():
        globals()[key] = _coerce_runtime_value(key, value)
    return dict(_RUNTIME_CONFIG)


def export_config(*, mask_sensitive: bool = False) -> dict[str, Any]:
    payload = dict(_RUNTIME_CONFIG)
    if not mask_sensitive:
        return payload
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key in SENSITIVE_KEYS:
            if isinstance(value, str) and value:
                out[key] = "********"
                continue
            if isinstance(value, list | dict) and value:
                out[key] = "********"
                continue
            if value not in ("", None, [], {}):
                out[key] = "********"
                continue
            out[key] = value
        else:
            out[key] = value
    return out


def resolve_workspace_dir(agent_id: str | None = None) -> Path:
    return resolve_agent_workspace_dir(agent_id=agent_id, config=_RUNTIME_CONFIG)


def explain_workspace_dir(agent_id: str | None = None) -> dict[str, Any]:
    return explain_workspace_resolution(agent_id=agent_id, config=_RUNTIME_CONFIG)


def read_snapshot() -> ConfigSnapshot:
    return read_config_snapshot()


def ensure_config_file() -> ConfigSnapshot:
    snapshot = read_config_snapshot()
    if snapshot.exists:
        return snapshot
    ok, next_snapshot, _changed, _restart, issues = write_config(dict(DEFAULTS))
    if not ok:
        message = "; ".join(f"{item.get('path')}: {item.get('message')}" for item in issues)
        raise RuntimeError(f"failed to initialize config file: {message}")
    reload()
    return next_snapshot


def write(
    patch: dict[str, Any],
    *,
    base_hash: str | None = None,
    unset_keys: list[str] | None = None,
) -> tuple[bool, ConfigSnapshot, list[str], list[str], list[dict[str, str]]]:
    result = write_config(patch, base_hash=base_hash, unset_keys=unset_keys)
    if result[0]:
        reload()
    return result


def __getattr__(name: str) -> Any:
    if name in _RUNTIME_CONFIG:
        return _coerce_runtime_value(name, _RUNTIME_CONFIG[name])
    if name in DEFAULTS:
        value = DEFAULTS[name]
        return _coerce_runtime_value(name, value)
    raise AttributeError(name)


reload()
