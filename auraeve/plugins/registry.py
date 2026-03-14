"""PluginRegistry：插件注册与管理。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from .base import Plugin
from .discovery import discover_plugin_manifests
from .hooks import HookRunner
from .loader import _is_enabled, load_plugin_from_manifest


class PluginRegistry:
    """
    插件注册表。

    使用方式：
        registry = PluginRegistry()
        registry.register(MyPlugin())
        hook_runner = registry.build_hook_runner()
    """

    def __init__(self) -> None:
        self._plugins: list[Plugin] = []

    def register(self, plugin: Plugin) -> None:
        """注册一个插件。"""
        existing_ids = {p.id for p in self._plugins}
        if plugin.id in existing_ids:
            logger.warning(f"[plugins] 插件 '{plugin.id}' 已存在，跳过重复注册")
            return
        self._plugins.append(plugin)
        logger.info(f"[plugins] 已注册插件: {plugin.id}")

    def register_discovered(
        self,
        *,
        workspace: Path,
        auto_discovery_enabled: bool,
        enabled: bool,
        allow: list[str] | None,
        deny: list[str] | None,
        load_paths: list[str] | None,
        entries: dict[str, Any] | None,
    ) -> list[str]:
        loaded_ids: list[str] = []
        if not auto_discovery_enabled:
            return loaded_ids

        manifests = discover_plugin_manifests(workspace=workspace, extra_paths=load_paths)
        for manifest in manifests:
            if not _is_enabled(
                manifest.plugin_id,
                enabled=enabled,
                allow=allow,
                deny=deny,
                entries=entries,
            ):
                logger.info(f"[plugins] 插件已禁用，跳过：{manifest.plugin_id}")
                continue
            plugin = load_plugin_from_manifest(manifest)
            if plugin is None:
                continue
            self.register(plugin)
            loaded_ids.append(plugin.id)
        return loaded_ids

    def unregister(self, plugin_id: str) -> bool:
        """注销一个插件，返回是否成功。"""
        before = len(self._plugins)
        self._plugins = [p for p in self._plugins if p.id != plugin_id]
        return len(self._plugins) < before

    def build_hook_runner(self) -> HookRunner:
        """构建 HookRunner 实例（包含所有已注册插件）。"""
        return HookRunner(list(self._plugins))

    @property
    def plugin_ids(self) -> list[str]:
        return [p.id for p in self._plugins]

    def __len__(self) -> int:
        return len(self._plugins)
