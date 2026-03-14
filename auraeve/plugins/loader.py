from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from loguru import logger

from .base import Plugin
from .manifest import PluginManifest


def _is_enabled(
    plugin_id: str,
    *,
    enabled: bool,
    allow: list[str] | None,
    deny: list[str] | None,
    entries: dict[str, Any] | None,
) -> bool:
    if not enabled:
        return False
    deny_set = set(deny or [])
    if plugin_id in deny_set:
        return False
    allow_set = set(allow or [])
    if allow_set and plugin_id not in allow_set:
        return False
    if entries and plugin_id in entries:
        entry_cfg = entries.get(plugin_id) or {}
        if isinstance(entry_cfg, dict) and entry_cfg.get("enabled") is False:
            return False
    return True


def _is_entry_inside_root(entry_path: Path, root: Path) -> bool:
    try:
        return entry_path.resolve().is_relative_to(root.resolve())
    except Exception:
        return False


def load_plugin_from_manifest(manifest: PluginManifest) -> Plugin | None:
    entry_path: Path = manifest.entry_path
    if not _is_entry_inside_root(entry_path, manifest.root):
        logger.warning(f"[plugins] 插件入口越界：{entry_path}")
        return None

    if not entry_path.exists() or not entry_path.is_file():
        logger.warning(f"[plugins] 插件入口不存在：{entry_path}")
        return None

    try:
        spec = importlib.util.spec_from_file_location(
            f"auraeve_plugin_{manifest.plugin_id}",
            str(entry_path),
        )
        if spec is None or spec.loader is None:
            logger.warning(f"[plugins] 无法加载插件 spec：{entry_path}")
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        logger.error(f"[plugins] 加载插件模块失败：{manifest.plugin_id} ({exc})")
        return None

    candidate = getattr(module, "plugin", None)
    if candidate is None:
        factory = getattr(module, "create_plugin", None)
        if callable(factory):
            try:
                candidate = factory()
            except Exception as exc:
                logger.error(f"[plugins] create_plugin 调用失败：{manifest.plugin_id} ({exc})")
                return None

    if candidate is None:
        cls = getattr(module, "PluginImpl", None)
        if cls is not None:
            try:
                candidate = cls()
            except Exception as exc:
                logger.error(f"[plugins] PluginImpl 实例化失败：{manifest.plugin_id} ({exc})")
                return None

    if not isinstance(candidate, Plugin):
        logger.warning(f"[plugins] 插件对象不合法（需继承 Plugin）：{manifest.plugin_id}")
        return None

    return candidate
