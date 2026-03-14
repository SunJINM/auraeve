from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from auraeve.config.paths import resolve_state_dir
from auraeve.config.stores import load_json_file, save_json_file_atomic


@dataclass
class EffectivePluginSettings:
    enabled: bool
    allow: list[str]
    deny: list[str]
    load_paths: list[str]
    entries: dict[str, dict[str, Any]]
    installs: dict[str, dict[str, Any]]

def resolve_extensions_dir() -> Path:
    return resolve_state_dir() / "plugins" / "extensions"


def resolve_plugins_state_path() -> Path:
    return resolve_state_dir() / "plugins" / "state.json"


def _normalize_str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _normalize_entries(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if isinstance(value, dict):
            out[key.strip()] = dict(value)
        else:
            out[key.strip()] = {}
    return out


def _normalize_installs(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(value, dict):
            continue
        out[key.strip()] = dict(value)
    return out


def load_plugin_state() -> dict[str, Any]:
    path = resolve_plugins_state_path()
    payload = load_json_file(path, {})
    if not isinstance(payload, dict):
        payload = {}

    return {
        "entries": _normalize_entries(payload.get("entries")),
        "load_paths": _normalize_str_list(payload.get("load_paths")),
        "installs": _normalize_installs(payload.get("installs")),
    }


def save_plugin_state(state: dict[str, Any]) -> None:
    target = {
        "entries": _normalize_entries(state.get("entries")),
        "load_paths": _normalize_str_list(state.get("load_paths")),
        "installs": _normalize_installs(state.get("installs")),
    }
    path = resolve_plugins_state_path()
    save_json_file_atomic(path, target)


def merge_plugin_settings_from_config(config: dict[str, Any]) -> EffectivePluginSettings:
    state = load_plugin_state()

    cfg_allow = _normalize_str_list(config.get("PLUGINS_ALLOW"))
    cfg_deny = _normalize_str_list(config.get("PLUGINS_DENY"))
    cfg_load_paths = _normalize_str_list(config.get("PLUGINS_LOAD_PATHS"))
    cfg_entries = _normalize_entries(config.get("PLUGINS_ENTRIES"))

    state_allow = _normalize_str_list(state.get("allow"))
    state_deny = _normalize_str_list(state.get("deny"))
    state_load_paths = _normalize_str_list(state.get("load_paths"))
    state_entries = _normalize_entries(state.get("entries"))

    merged_allow = list(dict.fromkeys(cfg_allow + state_allow))
    merged_deny = list(dict.fromkeys(cfg_deny + state_deny))
    merged_load_paths = list(dict.fromkeys(cfg_load_paths + state_load_paths))

    merged_entries = dict(cfg_entries)
    for key, value in state_entries.items():
        merged_entries[key] = {**merged_entries.get(key, {}), **value}

    enabled = bool(config.get("PLUGINS_ENABLED", True))

    return EffectivePluginSettings(
        enabled=enabled,
        allow=merged_allow,
        deny=merged_deny,
        load_paths=merged_load_paths,
        entries=merged_entries,
        installs=_normalize_installs(state.get("installs")),
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
