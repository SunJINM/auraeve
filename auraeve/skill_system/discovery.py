from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from auraeve.plugins.discovery import discover_plugin_manifests
from auraeve.plugins.loader import _is_enabled
from auraeve.plugins.state import merge_plugin_settings_from_config

from .manifest import parse_skill_entry
from .models import SkillEntry
from .state import resolve_managed_skills_dir


def resolve_builtin_skills_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "skills"


def _scan_skill_root(root: Path, source: str, max_skill_file_bytes: int) -> list[SkillEntry]:
    if not root.exists() or not root.is_dir():
        return []
    entries: list[SkillEntry] = []

    direct = root / "SKILL.md"
    if direct.exists() and direct.is_file():
        try:
            if direct.stat().st_size <= max_skill_file_bytes:
                item = parse_skill_entry(root, source)
                if item:
                    entries.append(item)
        except Exception:
            pass
        return entries

    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        skill_file = child / "SKILL.md"
        if not skill_file.exists() or not skill_file.is_file():
            continue
        try:
            if skill_file.stat().st_size > max_skill_file_bytes:
                continue
        except Exception:
            continue
        item = parse_skill_entry(child, source)
        if item:
            entries.append(item)
    return entries


def _resolve_plugin_skill_dirs(workspace: Path) -> list[Path]:
    try:
        import auraeve.config as cfg
    except Exception:
        return []

    plugin_cfg: dict[str, Any] = {
        "PLUGINS_ENABLED": getattr(cfg, "PLUGINS_ENABLED", True),
        "PLUGINS_ALLOW": getattr(cfg, "PLUGINS_ALLOW", []),
        "PLUGINS_DENY": getattr(cfg, "PLUGINS_DENY", []),
        "PLUGINS_LOAD_PATHS": getattr(cfg, "PLUGINS_LOAD_PATHS", []),
        "PLUGINS_ENTRIES": getattr(cfg, "PLUGINS_ENTRIES", {}),
    }
    settings = merge_plugin_settings_from_config(plugin_cfg)
    manifests = discover_plugin_manifests(workspace=workspace, extra_paths=settings.load_paths)

    out: list[Path] = []
    seen: set[str] = set()
    for manifest in manifests:
        if not _is_enabled(
            manifest.plugin_id,
            enabled=settings.enabled,
            allow=settings.allow,
            deny=settings.deny,
            entries=settings.entries,
        ):
            continue
        for rel in manifest.skills or []:
            p = (manifest.root / rel).resolve()
            if not p.exists() or not p.is_dir():
                continue
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
    return out


def discover_skill_entries(
    workspace: Path,
    *,
    extra_dirs: list[str] | None = None,
    max_skill_file_bytes: int = 256_000,
) -> list[SkillEntry]:
    workspace = workspace.resolve()
    managed = resolve_managed_skills_dir()
    workspace_skills = (workspace / "skills").resolve()
    builtin = resolve_builtin_skills_dir().resolve()

    plugin_dirs = _resolve_plugin_skill_dirs(workspace)
    normalized_extra = []
    for raw in extra_dirs or []:
        val = str(raw).strip()
        if not val:
            continue
        normalized_extra.append(Path(os.path.expanduser(val)).resolve())

    sources: list[tuple[Path, str]] = [
        (builtin, "builtin"),
        *[(p, "plugin") for p in plugin_dirs],
        (managed, "managed"),
        (workspace_skills, "workspace"),
    ]
    sources.extend((p, "extra") for p in normalized_extra)

    merged: dict[str, SkillEntry] = {}
    for root, source in sources:
        for entry in _scan_skill_root(root, source, max_skill_file_bytes):
            merged[entry.name] = entry
    return list(merged.values())
