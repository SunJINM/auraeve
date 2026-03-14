from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass
class PluginManifest:
    plugin_id: str
    entry: str
    root: Path
    manifest_path: Path
    raw: dict[str, Any] = field(default_factory=dict)
    origin: str = "unknown"
    name: str | None = None
    description: str | None = None
    version: str | None = None
    skills: list[str] | None = None
    config_schema: dict[str, Any] | None = None

    @property
    def entry_path(self) -> Path:
        return (self.root / self.entry).resolve()


def parse_plugin_manifest(
    manifest_path: Path,
    *,
    origin: str = "unknown",
) -> tuple[PluginManifest | None, str | None]:
    try:
        raw_text = manifest_path.read_text(encoding="utf-8-sig")
        data = json.loads(raw_text)
    except Exception as exc:
        return None, f"读取 manifest 失败：{manifest_path} ({exc})"

    if not isinstance(data, dict):
        return None, f"manifest 必须是对象：{manifest_path}"

    plugin_id = str(data.get("id") or "").strip()
    entry = str(data.get("entry") or "").strip()
    if not plugin_id or not entry:
        return None, f"manifest 缺少 id 或 entry：{manifest_path}"

    raw_skills = data.get("skills")
    skills: list[str] = []
    if isinstance(raw_skills, list):
        for item in raw_skills:
            if isinstance(item, str):
                normalized = item.strip()
                if normalized:
                    skills.append(normalized)

    config_schema = data.get("configSchema")
    normalized_schema = config_schema if isinstance(config_schema, dict) else None

    return (
        PluginManifest(
            plugin_id=plugin_id,
            entry=entry,
            root=manifest_path.parent.resolve(),
            manifest_path=manifest_path.resolve(),
            origin=origin,
            name=str(data.get("name") or "").strip() or None,
            description=str(data.get("description") or "").strip() or None,
            version=str(data.get("version") or "").strip() or None,
            skills=skills,
            config_schema=normalized_schema,
            raw=data,
        ),
        None,
    )
