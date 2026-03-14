from __future__ import annotations

from pathlib import Path
from typing import Any

from auraeve.config.paths import resolve_state_dir
from auraeve.config.stores import load_json_file, save_json_file_atomic

from .models import SkillStateEntry, SkillsInstallPreferences


DEFAULT_SKILLS_STATE = {
    "entries": {},
    "install": {
        "nodeManager": "npm",
        "preferBrew": True,
        "timeoutMs": 300000,
        "allowDownloadDomains": [],
    },
    "installs": {},
    "uploads": {},
    "locks": {},
    "load": {"extraDirs": []},
}

def resolve_skills_state_path() -> Path:
    return resolve_state_dir() / "skills" / "state.json"


def resolve_managed_skills_dir() -> Path:
    return resolve_state_dir() / "skills" / "managed"


def resolve_tools_dir() -> Path:
    return resolve_state_dir() / "tools"


def _normalize_str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        val = item.strip()
        if not val or val in seen:
            continue
        seen.add(val)
        out.append(val)
    return out


def _normalize_entries(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            continue
        k = key.strip()
        if not isinstance(value, dict):
            out[k] = {}
            continue
        entry = dict(value)
        env = entry.get("env")
        if not isinstance(env, dict):
            entry["env"] = {}
        else:
            entry["env"] = {str(ek).strip(): str(ev) for ek, ev in env.items() if str(ek).strip()}
        cfg = entry.get("config")
        if not isinstance(cfg, dict):
            entry["config"] = {}
        out[k] = entry
    return out


def _normalize_install(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    node_manager = str(raw.get("nodeManager", "npm")).strip().lower()
    if node_manager not in {"npm", "pnpm", "yarn", "bun"}:
        node_manager = "npm"
    timeout_ms = raw.get("timeoutMs", 300000)
    if not isinstance(timeout_ms, int):
        timeout_ms = 300000
    timeout_ms = min(max(timeout_ms, 1000), 900000)
    return {
        "nodeManager": node_manager,
        "preferBrew": bool(raw.get("preferBrew", True)),
        "timeoutMs": timeout_ms,
        "allowDownloadDomains": _normalize_str_list(raw.get("allowDownloadDomains")),
    }


def load_skills_state() -> dict[str, Any]:
    path = resolve_skills_state_path()
    payload = load_json_file(path, {})
    if not path.exists():
        return dict(DEFAULT_SKILLS_STATE)

    if not isinstance(payload, dict):
        payload = {}

    return {
        "entries": _normalize_entries(payload.get("entries")),
        "install": _normalize_install(payload.get("install")),
        "installs": payload.get("installs") if isinstance(payload.get("installs"), dict) else {},
        "uploads": payload.get("uploads") if isinstance(payload.get("uploads"), dict) else {},
        "locks": payload.get("locks") if isinstance(payload.get("locks"), dict) else {},
        "load": {
            "extraDirs": _normalize_str_list((payload.get("load") or {}).get("extraDirs"))
            if isinstance(payload.get("load"), dict)
            else []
        },
    }


def save_skills_state(state: dict[str, Any]) -> None:
    path = resolve_skills_state_path()
    normalized = {
        "entries": _normalize_entries(state.get("entries")),
        "install": _normalize_install(state.get("install")),
        "installs": state.get("installs") if isinstance(state.get("installs"), dict) else {},
        "uploads": state.get("uploads") if isinstance(state.get("uploads"), dict) else {},
        "locks": state.get("locks") if isinstance(state.get("locks"), dict) else {},
        "load": {
            "extraDirs": _normalize_str_list((state.get("load") or {}).get("extraDirs"))
            if isinstance(state.get("load"), dict)
            else []
        },
    }
    save_json_file_atomic(path, normalized)


def resolve_entry_settings(state: dict[str, Any], skill_key: str) -> SkillStateEntry:
    entries = state.get("entries") if isinstance(state.get("entries"), dict) else {}
    raw = entries.get(skill_key) if isinstance(entries, dict) else None
    if not isinstance(raw, dict):
        return SkillStateEntry()
    env_raw = raw.get("env")
    env = env_raw if isinstance(env_raw, dict) else {}
    cfg_raw = raw.get("config")
    cfg = cfg_raw if isinstance(cfg_raw, dict) else {}
    enabled = raw.get("enabled") if isinstance(raw.get("enabled"), bool) else None
    api_key = raw.get("apiKey") if isinstance(raw.get("apiKey"), str) else None
    return SkillStateEntry(enabled=enabled, env={str(k): str(v) for k, v in env.items()}, api_key=api_key, config=dict(cfg))


def resolve_install_preferences(state: dict[str, Any]) -> SkillsInstallPreferences:
    install = state.get("install") if isinstance(state.get("install"), dict) else {}
    return SkillsInstallPreferences(
        node_manager=str(install.get("nodeManager", "npm")),
        prefer_brew=bool(install.get("preferBrew", True)),
        timeout_ms=int(install.get("timeoutMs", 300000)),
        allow_download_domains=_normalize_str_list(install.get("allowDownloadDomains")),
    )
