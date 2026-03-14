from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import auraeve.config as cfg
from .discovery import discover_plugin_manifests
from .install import (
    build_install_record,
    install_plugin_from_local_path,
)
from .loader import _is_enabled
from .state import (
    EffectivePluginSettings,
    load_plugin_state,
    merge_plugin_settings_from_config,
    resolve_extensions_dir,
    save_plugin_state,
)


@dataclass
class PluginRecord:
    id: str
    enabled: bool
    reason: str | None
    origin: str
    root: str
    manifest_path: str
    entry: str
    entry_exists: bool
    version: str | None
    description: str | None
    skills: list[str]
    install: dict[str, Any] | None = None


def _read_runtime_config() -> dict[str, Any]:
    import auraeve.config as cfg

    return {
        "PLUGINS_ENABLED": getattr(cfg, "PLUGINS_ENABLED", True),
        "PLUGINS_ALLOW": getattr(cfg, "PLUGINS_ALLOW", []),
        "PLUGINS_DENY": getattr(cfg, "PLUGINS_DENY", []),
        "PLUGINS_LOAD_PATHS": getattr(cfg, "PLUGINS_LOAD_PATHS", []),
        "PLUGINS_ENTRIES": getattr(cfg, "PLUGINS_ENTRIES", {}),
    }


def resolve_effective_settings() -> EffectivePluginSettings:
    return merge_plugin_settings_from_config(_read_runtime_config())


def list_plugins(workspace: Path) -> list[PluginRecord]:
    settings = resolve_effective_settings()
    manifests = discover_plugin_manifests(workspace=workspace, extra_paths=settings.load_paths)
    out: list[PluginRecord] = []

    for manifest in manifests:
        enabled = _is_enabled(
            manifest.plugin_id,
            enabled=settings.enabled,
            allow=settings.allow,
            deny=settings.deny,
            entries=settings.entries,
        )
        reason: str | None = None
        if not settings.enabled:
            reason = "plugins disabled"
        elif manifest.plugin_id in set(settings.deny):
            reason = "denied by configuration"
        elif settings.allow and manifest.plugin_id not in set(settings.allow):
            reason = "not in allowlist"
        elif settings.entries.get(manifest.plugin_id, {}).get("enabled") is False:
            reason = "disabled in entries"

        out.append(
            PluginRecord(
                id=manifest.plugin_id,
                enabled=enabled,
                reason=reason,
                origin=manifest.origin,
                root=str(manifest.root),
                manifest_path=str(manifest.manifest_path),
                entry=manifest.entry,
                entry_exists=manifest.entry_path.exists(),
                version=manifest.version,
                description=manifest.description,
                skills=list(manifest.skills or []),
                install=settings.installs.get(manifest.plugin_id),
            )
        )

    out.sort(key=lambda x: x.id)
    return out


def get_plugin_info(workspace: Path, plugin_id: str) -> PluginRecord | None:
    for item in list_plugins(workspace):
        if item.id == plugin_id:
            return item
    return None


def _read_state() -> dict[str, Any]:
    return load_plugin_state()


def _write_state(state: dict[str, Any]) -> None:
    save_plugin_state(state)


def enable_plugin(plugin_id: str, enabled: bool) -> dict[str, Any]:
    state = _read_state()
    entries = state.setdefault("entries", {})
    if not isinstance(entries, dict):
        entries = {}
        state["entries"] = entries

    entry = entries.get(plugin_id)
    if not isinstance(entry, dict):
        entry = {}

    entry["enabled"] = bool(enabled)
    entries[plugin_id] = entry
    _write_state(state)

    return {"ok": True, "id": plugin_id, "enabled": bool(enabled)}

def _looks_like_clawhub_input(path_input: str) -> bool:
    raw = (path_input or "").strip().lower().replace("\\", "/")
    return (
        raw.startswith("clawhub:")
        or raw.startswith("clawhub://")
        or raw.startswith("https://clawhub.ai/")
        or raw.startswith("http://clawhub.ai/")
        or raw.startswith("https://www.clawhub.ai/")
        or raw.startswith("http://www.clawhub.ai/")
    )


def install_plugin(path_input: str, *, link: bool = False, overwrite: bool = False) -> dict[str, Any]:
    state = _read_state()
    if _looks_like_clawhub_input(path_input):
        return {
            "ok": False,
            "message": (
                "clawhub 中发布的是 skill，不是插件；"
                "plugins install 仅支持本地插件路径/压缩包。"
            ),
        }

    source = Path(path_input).expanduser().resolve()
    if not source.exists():
        return {"ok": False, "message": f"path not found: {source}"}

    if link:
        manifests = discover_plugin_manifests(
            workspace=cfg.resolve_workspace_dir("default"),
            extra_paths=[str(source)],
        )
        if not manifests:
            return {"ok": False, "message": "link path does not contain a valid plugin manifest"}

        plugin_id = manifests[0].plugin_id
        load_paths = state.setdefault("load_paths", [])
        if not isinstance(load_paths, list):
            load_paths = []
            state["load_paths"] = load_paths
        if str(source) not in load_paths:
            load_paths.append(str(source))

        entries = state.setdefault("entries", {})
        if not isinstance(entries, dict):
            entries = {}
            state["entries"] = entries
        entry = entries.get(plugin_id)
        if not isinstance(entry, dict):
            entry = {}
        entry["enabled"] = True
        entries[plugin_id] = entry

        installs = state.setdefault("installs", {})
        if not isinstance(installs, dict):
            installs = {}
            state["installs"] = installs
        installs[plugin_id] = {
            "source": "path-link",
            "source_path": str(source),
            "install_path": str(source),
            "version": manifests[0].version,
        }

        _write_state(state)
        return {
            "ok": True,
            "id": plugin_id,
            "message": f"linked plugin path: {source}",
        }

    result = install_plugin_from_local_path(str(source), overwrite=overwrite)
    if not result.ok or not result.plugin_id:
        return {"ok": False, "message": result.message or "install failed"}

    installs = state.setdefault("installs", {})
    if not isinstance(installs, dict):
        installs = {}
        state["installs"] = installs
    installs[result.plugin_id] = build_install_record(result)

    entries = state.setdefault("entries", {})
    if not isinstance(entries, dict):
        entries = {}
        state["entries"] = entries
    entry = entries.get(result.plugin_id)
    if not isinstance(entry, dict):
        entry = {}
    entry["enabled"] = True
    entries[result.plugin_id] = entry

    _write_state(state)

    return {
        "ok": True,
        "id": result.plugin_id,
        "installPath": result.install_path,
        "message": result.message,
    }


def uninstall_plugin(plugin_id: str, *, keep_files: bool = False) -> dict[str, Any]:
    state = _read_state()

    entries = state.get("entries") if isinstance(state.get("entries"), dict) else {}
    installs = state.get("installs") if isinstance(state.get("installs"), dict) else {}
    load_paths = state.get("load_paths") if isinstance(state.get("load_paths"), list) else []

    install_record = installs.get(plugin_id) if isinstance(installs, dict) else None

    if isinstance(entries, dict) and plugin_id in entries:
        entries.pop(plugin_id, None)
    if isinstance(installs, dict) and plugin_id in installs:
        installs.pop(plugin_id, None)

    if isinstance(load_paths, list):
        state["load_paths"] = [
            p
            for p in load_paths
            if not (
                isinstance(install_record, dict)
                and isinstance(install_record.get("source_path"), str)
                and p == install_record["source_path"]
            )
        ]

    state["entries"] = entries
    state["installs"] = installs
    _write_state(state)

    removed_files = False
    if not keep_files:
        candidate = resolve_extensions_dir() / plugin_id
        if candidate.exists() and candidate.is_dir():
            shutil.rmtree(candidate, ignore_errors=True)
            removed_files = True

    return {
        "ok": True,
        "id": plugin_id,
        "removedFiles": removed_files,
    }


def plugin_doctor(workspace: Path) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    plugins = list_plugins(workspace)

    ids = [p.id for p in plugins]
    duplicates = {i for i in ids if ids.count(i) > 1}
    for dup in sorted(duplicates):
        issues.append({"code": "duplicate_id", "message": f"duplicate plugin id: {dup}"})

    for plugin in plugins:
        if not plugin.entry_exists:
            issues.append(
                {
                    "code": "missing_entry",
                    "pluginId": plugin.id,
                    "message": f"entry not found: {plugin.entry}",
                }
            )

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "plugins": [asdict(p) for p in plugins],
    }
