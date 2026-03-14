from __future__ import annotations

from pathlib import Path
from typing import Any

from auraeve.plugins.service import (
    enable_plugin,
    get_plugin_info,
    install_plugin,
    list_plugins,
    plugin_doctor,
    uninstall_plugin,
)


class PluginWebService:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def list(self) -> dict[str, Any]:
        records = list_plugins(self.workspace)
        return {
            "ok": True,
            "plugins": [
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
            ],
        }

    def info(self, plugin_id: str) -> dict[str, Any]:
        record = get_plugin_info(self.workspace, plugin_id)
        if record is None:
            return {"ok": False, "message": f"plugin not found: {plugin_id}"}

        return {
            "ok": True,
            "plugin": {
                "id": record.id,
                "enabled": record.enabled,
                "reason": record.reason,
                "origin": record.origin,
                "root": record.root,
                "manifestPath": record.manifest_path,
                "entry": record.entry,
                "entryExists": record.entry_exists,
                "version": record.version,
                "description": record.description,
                "skills": record.skills,
                "install": record.install,
            },
        }

    def install(self, path: str, link: bool = False) -> dict[str, Any]:
        return install_plugin(path, link=link)

    def uninstall(self, plugin_id: str, keep_files: bool = False) -> dict[str, Any]:
        return uninstall_plugin(plugin_id, keep_files=keep_files)

    def enable(self, plugin_id: str) -> dict[str, Any]:
        return enable_plugin(plugin_id, True)

    def disable(self, plugin_id: str) -> dict[str, Any]:
        return enable_plugin(plugin_id, False)

    def doctor(self) -> dict[str, Any]:
        return plugin_doctor(self.workspace)
