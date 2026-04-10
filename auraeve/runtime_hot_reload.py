from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from auraeve.plugins import PluginRegistry
from auraeve.stt import runtime_config_from_dict

CORE_RUNTIME_KEYS = {
    "LLM_TEMPERATURE",
    "LLM_MAX_TOKENS",
    "LLM_MAX_TOOL_ITERATIONS",
    "RUNTIME_EXECUTION",
    "RUNTIME_LOOP_GUARD",
    "LLM_MEMORY_WINDOW",
    "TOKEN_BUDGET",
    "SESSION_TOOL_POLICY",
    "GLOBAL_DENY_TOOLS",
}
HEARTBEAT_KEYS = {"HEARTBEAT_ENABLED", "HEARTBEAT_INTERVAL_S"}
CHANNEL_KEYS = {
    "DINGTALK_ENABLED",
    "DINGTALK_CLIENT_ID",
    "DINGTALK_CLIENT_SECRET",
    "DINGTALK_ALLOW_FROM",
    "NAPCAT_ENABLED",
    "NAPCAT_WS_URL",
    "NAPCAT_ACCESS_TOKEN",
    "NAPCAT_ALLOW_FROM",
    "NAPCAT_ALLOW_GROUPS",
    "CHANNEL_USERS",
    "NOTIFY_CHANNEL",
}
STT_KEYS = {
    "ASR",
}
PLUGIN_KEYS = {
    "PLUGINS_AUTO_DISCOVERY_ENABLED",
    "PLUGINS_ENABLED",
    "PLUGINS_LOAD_PATHS",
    "PLUGINS_ALLOW",
    "PLUGINS_DENY",
    "PLUGINS_ENTRIES",
}
SKILL_KEYS = {
    "SKILLS_ENABLED",
    "SKILLS_ENTRIES",
    "SKILLS_LOAD_EXTRA_DIRS",
    "SKILLS_INSTALL_NODE_MANAGER",
    "SKILLS_INSTALL_PREFER_BREW",
    "SKILLS_INSTALL_TIMEOUT_MS",
    "SKILLS_SECURITY_ALLOWED_DOWNLOAD_DOMAINS",
    "SKILLS_LIMIT_MAX_IN_PROMPT",
    "SKILLS_LIMIT_MAX_PROMPT_CHARS",
    "SKILLS_LIMIT_MAX_FILE_BYTES",
}


@dataclass
class ChannelRuntimeControls:
    is_dingtalk_configured: Callable[[], bool]
    restart_dingtalk_channel: Callable[[], Awaitable[bool]]
    stop_dingtalk_channel: Callable[[], Awaitable[None]]
    get_dingtalk_channel: Callable[[], Any | None]
    is_napcat_enabled: Callable[[], bool]
    restart_napcat_channel: Callable[[], Awaitable[bool]]
    stop_napcat_channel: Callable[[], Awaitable[None]]
    get_napcat_channel: Callable[[], Any | None]


class RuntimeHotApplyService:
    def __init__(
        self,
        *,
        config,
        agent,
        heartbeat,
        stt_runtime,
        engine,
        workspace,
        plugin_registry,
        plugin_registry_factory: Callable[[], PluginRegistry],
        merge_plugin_settings: Callable[[dict], Any],
        channel_runtime: ChannelRuntimeControls,
        message_tool_sync: Callable[..., None],
        export_config: Callable[[], dict] | None = None,
    ) -> None:
        self.config = config
        self.agent = agent
        self.heartbeat = heartbeat
        self.stt_runtime = stt_runtime
        self.engine = engine
        self.workspace = workspace
        self.plugin_registry = plugin_registry
        self.plugin_registry_factory = plugin_registry_factory
        self.merge_plugin_settings = merge_plugin_settings
        self.channel_runtime = channel_runtime
        self.message_tool_sync = message_tool_sync
        self.export_config = export_config or (lambda: self.config.export_config(mask_sensitive=False))

    async def apply(self, new_config: dict, hot_keys: list[str]) -> dict:
        if not getattr(self.config, "RUNTIME_HOT_APPLY_ENABLED", True):
            return {"applied": [], "requiresRestart": list(hot_keys), "issues": []}

        applied: set[str] = set()
        restart: set[str] = set()
        issues: list[dict[str, str]] = []
        remaining = set(hot_keys)

        def merge_runtime_result(result: dict) -> None:
            applied.update(result.get("applied") or [])
            restart.update(result.get("requiresRestart") or [])
            runtime_issues = result.get("issues") or []
            if isinstance(runtime_issues, list):
                for item in runtime_issues:
                    if isinstance(item, dict):
                        issues.append(item)

        core_patch = {key: new_config[key] for key in remaining if key in CORE_RUNTIME_KEYS and key in new_config}
        if core_patch:
            merge_runtime_result(await self.agent.reload_runtime_config(core_patch))
            remaining -= set(core_patch.keys())

        heartbeat_patch = {key: new_config[key] for key in remaining if key in HEARTBEAT_KEYS and key in new_config}
        if heartbeat_patch:
            if "HEARTBEAT_INTERVAL_S" in heartbeat_patch:
                self.heartbeat.interval_s = int(heartbeat_patch["HEARTBEAT_INTERVAL_S"])
                applied.add("HEARTBEAT_INTERVAL_S")
            if "HEARTBEAT_ENABLED" in heartbeat_patch:
                desired_enabled = bool(heartbeat_patch["HEARTBEAT_ENABLED"])
                self.heartbeat.enabled = desired_enabled
                if desired_enabled and not getattr(self.heartbeat, "_running", False):
                    await self.heartbeat.start()
                if not desired_enabled and getattr(self.heartbeat, "_running", False):
                    self.heartbeat.stop()
                applied.add("HEARTBEAT_ENABLED")
            remaining -= set(heartbeat_patch.keys())

        if "MCP" in remaining and "MCP" in new_config:
            merge_runtime_result(await self.agent.reload_runtime_config({"MCP": new_config["MCP"]}))
            remaining.discard("MCP")

        stt_patch_keys = {key for key in remaining if key in STT_KEYS}
        if stt_patch_keys:
            try:
                self.stt_runtime.reload(runtime_config_from_dict(self.export_config()))
                applied.update(stt_patch_keys)
            except Exception as exc:
                restart.update(stt_patch_keys)
                issues.append({"code": "stt_hot_reload_failed", "message": str(exc)})
            remaining -= stt_patch_keys

        await self._apply_channel_changes(new_config, remaining, applied, restart, issues)
        remaining -= {key for key in remaining if key in CHANNEL_KEYS}

        plugin_patch_keys = {key for key in remaining if key in PLUGIN_KEYS}
        if plugin_patch_keys:
            try:
                self.plugin_registry = self._reload_plugins()
                applied.update(plugin_patch_keys)
            except Exception as exc:
                restart.update(plugin_patch_keys)
                issues.append({"code": "plugins_hot_reload_failed", "message": str(exc)})
            remaining -= plugin_patch_keys

        skill_patch_keys = {key for key in remaining if key in SKILL_KEYS}
        if skill_patch_keys:
            try:
                self._reload_skills()
                applied.update(skill_patch_keys)
            except Exception as exc:
                restart.update(skill_patch_keys)
                issues.append({"code": "skills_hot_reload_failed", "message": str(exc)})
            remaining -= skill_patch_keys

        if remaining:
            restart.update(remaining)
            issues.append(
                {
                    "code": "runtime_hot_key_unhandled",
                    "message": f"unhandled hot keys: {', '.join(sorted(remaining))}",
                }
            )

        return {
            "applied": sorted(applied),
            "requiresRestart": sorted(restart),
            "issues": issues,
        }

    async def _apply_channel_changes(
        self,
        new_config: dict,
        remaining: set[str],
        applied: set[str],
        restart: set[str],
        issues: list[dict[str, str]],
    ) -> None:
        channel_patch_keys = {key for key in remaining if key in CHANNEL_KEYS}
        if not channel_patch_keys:
            return

        dingtalk_restart_keys = {"DINGTALK_ENABLED", "DINGTALK_CLIENT_ID", "DINGTALK_CLIENT_SECRET"}
        napcat_restart_keys = {"NAPCAT_ENABLED", "NAPCAT_WS_URL", "NAPCAT_ACCESS_TOKEN"}

        if channel_patch_keys & dingtalk_restart_keys:
            try:
                if self.channel_runtime.is_dingtalk_configured():
                    started = await self.channel_runtime.restart_dingtalk_channel()
                    if started:
                        applied.update(channel_patch_keys & dingtalk_restart_keys)
                    else:
                        restart.update(channel_patch_keys & dingtalk_restart_keys)
                else:
                    await self.channel_runtime.stop_dingtalk_channel()
                    applied.update(channel_patch_keys & dingtalk_restart_keys)
            except Exception as exc:
                restart.update(channel_patch_keys & dingtalk_restart_keys)
                issues.append({"code": "dingtalk_hot_reload_failed", "message": str(exc)})

        if channel_patch_keys & napcat_restart_keys:
            try:
                if self.channel_runtime.is_napcat_enabled():
                    started = await self.channel_runtime.restart_napcat_channel()
                    if started:
                        applied.update(channel_patch_keys & napcat_restart_keys)
                    else:
                        restart.update(channel_patch_keys & napcat_restart_keys)
                else:
                    await self.channel_runtime.stop_napcat_channel()
                    applied.update(channel_patch_keys & napcat_restart_keys)
            except Exception as exc:
                restart.update(channel_patch_keys & napcat_restart_keys)
                issues.append({"code": "napcat_hot_reload_failed", "message": str(exc)})

        for key in channel_patch_keys:
            if key in dingtalk_restart_keys or key in napcat_restart_keys:
                continue
            if key == "DINGTALK_ALLOW_FROM":
                channel = self.channel_runtime.get_dingtalk_channel()
                if channel is None:
                    restart.add(key)
                    issues.append({"code": "channel_not_running", "message": "dingtalk channel is not running"})
                else:
                    channel.config.allow_from = list(new_config.get(key) or [])
                    applied.add(key)
            elif key == "NAPCAT_ALLOW_FROM":
                channel = self.channel_runtime.get_napcat_channel()
                if channel is None:
                    restart.add(key)
                    issues.append({"code": "channel_not_running", "message": "napcat channel is not running"})
                else:
                    channel.config.allow_from = list(new_config.get(key) or [])
                    applied.add(key)
            elif key == "NAPCAT_ALLOW_GROUPS":
                channel = self.channel_runtime.get_napcat_channel()
                if channel is None:
                    restart.add(key)
                    issues.append({"code": "channel_not_running", "message": "napcat channel is not running"})
                else:
                    channel.config.allow_groups = list(new_config.get(key) or [])
                    applied.add(key)
            elif key == "CHANNEL_USERS":
                channel_users = dict(new_config.get(key) or {})
                self.agent._channel_users = channel_users
                self.message_tool_sync(channel_users=channel_users)
                applied.add(key)
            elif key == "NOTIFY_CHANNEL":
                notify_channel = str(new_config.get(key) or "")
                self.agent._notify_channel = notify_channel
                self.message_tool_sync(notify_channel=notify_channel)
                applied.add(key)

    def _reload_plugins(self):
        plugin_settings_next = self.merge_plugin_settings(
            {
                "PLUGINS_ENABLED": getattr(self.config, "PLUGINS_ENABLED", True),
                "PLUGINS_ALLOW": getattr(self.config, "PLUGINS_ALLOW", []),
                "PLUGINS_DENY": getattr(self.config, "PLUGINS_DENY", []),
                "PLUGINS_LOAD_PATHS": getattr(self.config, "PLUGINS_LOAD_PATHS", []),
                "PLUGINS_ENTRIES": getattr(self.config, "PLUGINS_ENTRIES", {}),
            }
        )
        next_registry = self.plugin_registry_factory()
        next_registry.register_discovered(
            workspace=self.workspace,
            auto_discovery_enabled=getattr(self.config, "PLUGINS_AUTO_DISCOVERY_ENABLED", True),
            enabled=plugin_settings_next.enabled,
            allow=plugin_settings_next.allow,
            deny=plugin_settings_next.deny,
            load_paths=plugin_settings_next.load_paths,
            entries=plugin_settings_next.entries,
        )
        hooks = next_registry.build_hook_runner()
        self.agent.hooks = hooks
        self.agent.assembler._hooks = hooks
        self.agent._runner._hooks = hooks
        return next_registry

    def _reload_skills(self) -> None:
        context_builder = None
        if hasattr(self.engine, "_builder"):
            context_builder = getattr(self.engine, "_builder")
        elif hasattr(self.engine, "_context_builder"):
            context_builder = getattr(self.engine, "_context_builder")
        if context_builder is None or not hasattr(context_builder, "skills"):
            return
        skills_loader = getattr(context_builder, "skills")
        if hasattr(skills_loader, "max_skills_in_prompt"):
            skills_loader.max_skills_in_prompt = int(getattr(self.config, "SKILLS_LIMIT_MAX_IN_PROMPT", 150))
        if hasattr(skills_loader, "max_skills_prompt_chars"):
            skills_loader.max_skills_prompt_chars = int(getattr(self.config, "SKILLS_LIMIT_MAX_PROMPT_CHARS", 30000))
        if hasattr(skills_loader, "max_skill_file_bytes"):
            skills_loader.max_skill_file_bytes = int(getattr(self.config, "SKILLS_LIMIT_MAX_FILE_BYTES", 256000))
        if hasattr(skills_loader, "invalidate_cache"):
            skills_loader.invalidate_cache()


def sync_message_tool_settings(agent, *, channel_users: dict | None = None, notify_channel: str | None = None) -> None:
    return None
