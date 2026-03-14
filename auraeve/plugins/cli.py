from __future__ import annotations

import json
from pathlib import Path

from .service import (
    enable_plugin,
    get_plugin_info,
    install_plugin,
    list_plugins,
    plugin_doctor,
    uninstall_plugin,
)


def _serialize_plugin_records(records):
    return [
        {
            "id": r.id,
            "enabled": r.enabled,
            "reason": r.reason,
            "origin": r.origin,
            "root": r.root,
            "manifestPath": r.manifest_path,
            "entry": r.entry,
            "entryExists": r.entry_exists,
            "version": r.version,
            "description": r.description,
            "skills": r.skills,
            "install": r.install,
        }
        for r in records
    ]


def list_command(workspace: Path, *, as_json: bool = False) -> int:
    records = list_plugins(workspace)
    if as_json:
        print(json.dumps({"plugins": _serialize_plugin_records(records)}, ensure_ascii=False, indent=2))
        return 0

    if not records:
        print("No plugins found.")
        return 0

    for r in records:
        status = "enabled" if r.enabled else "disabled"
        reason = f" ({r.reason})" if r.reason else ""
        print(f"- {r.id} [{status}] origin={r.origin}{reason}")
    return 0


def info_command(workspace: Path, plugin_id: str, *, as_json: bool = False) -> int:
    item = get_plugin_info(workspace, plugin_id)
    if item is None:
        print(f"Plugin not found: {plugin_id}")
        return 1

    payload = _serialize_plugin_records([item])[0]
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def install_command(path_input: str, *, link: bool = False) -> int:
    result = install_plugin(path_input, link=link)
    if not result.get("ok"):
        print(result.get("message") or "Install failed")
        return 1
    print(result.get("message") or "Installed")
    print("Restart auraeve process to apply plugin changes.")
    return 0


def uninstall_command(plugin_id: str, *, keep_files: bool = False) -> int:
    result = uninstall_plugin(plugin_id, keep_files=keep_files)
    if not result.get("ok"):
        print(result.get("message") or "Uninstall failed")
        return 1
    print(f"Uninstalled plugin: {plugin_id}")
    print("Restart auraeve process to apply plugin changes.")
    return 0


def enable_command(plugin_id: str) -> int:
    result = enable_plugin(plugin_id, True)
    if not result.get("ok"):
        print(result.get("message") or "Enable failed")
        return 1
    print(f"Enabled plugin: {plugin_id}")
    print("Restart auraeve process to apply plugin changes.")
    return 0


def disable_command(plugin_id: str) -> int:
    result = enable_plugin(plugin_id, False)
    if not result.get("ok"):
        print(result.get("message") or "Disable failed")
        return 1
    print(f"Disabled plugin: {plugin_id}")
    print("Restart auraeve process to apply plugin changes.")
    return 0


def doctor_command(workspace: Path, *, as_json: bool = False) -> int:
    report = plugin_doctor(workspace)
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok") else 1

    if report.get("ok"):
        print("Plugin doctor: OK")
        return 0

    print("Plugin doctor found issues:")
    for issue in report.get("issues") or []:
        print(f"- {issue.get('code')}: {issue.get('message')}")
    return 1


# keep naming symmetric for callers

def disable_plugin(plugin_id: str) -> dict:
    return enable_plugin(plugin_id, False)
