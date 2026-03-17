"""`r`nAuraEve entrypoint.`r`n`r`nRun:`r`n    python main.py`r`n"""

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

from loguru import logger

import auraeve.config as cfg
from auraeve.observability import init_observability
from auraeve.observability.loguru_sink import loguru_sink
from auraeve.bus.queue import MessageBus
from auraeve.channels.dingtalk import DingTalkChannel, DingTalkConfig
from auraeve.channels.terminal import TerminalChannel, TerminalConfig
from auraeve.channels.napcat import NapCatChannel, NapCatConfig
from auraeve.agent_runtime.kernel import RuntimeKernel
from auraeve.cron.service import CronService
from auraeve.plugins import PluginRegistry
from auraeve.plugins.state import merge_plugin_settings_from_config
from auraeve.heartbeat.service import HeartbeatService
from auraeve.utils.helpers import ensure_dir
from auraeve.channels.webui import WebUIChannel, WebUIChannelConfig
from auraeve.webui.chat_service import ChatService
from auraeve.webui.config_service import ConfigService
from auraeve.webui.server import WebUIServer
from auraeve.agent.tools.message import MessageTool
from auraeve.stt import build_runtime_from_config, runtime_config_from_dict
from auraeve.media_understanding import build_media_runtime_from_config
from auraeve.runtime_bootstrap import bootstrap_workspace_from_template
from auraeve.memory_lifecycle import MemoryLifecycleService


class _OpenAIEmbedder:
    """ OpenAI ?"""

    def __init__(self, api_key: str, api_base: str | None, model: str):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=api_key, base_url=api_base or None)
        self.model = model

    async def embed(self, text: str) -> list[float]:
        r = await self._client.embeddings.create(input=text, model=self.model)
        return r.data[0].embedding


def _build_provider():
    """Build OpenAI-compatible provider from loaded config values."""
    from auraeve.providers.openai_provider import OpenAICompatibleProvider

    return OpenAICompatibleProvider(
        api_key=cfg.LLM_API_KEY,
        api_base=cfg.LLM_API_BASE or None,
        default_model=cfg.LLM_MODEL,
        extra_headers=cfg.LLM_EXTRA_HEADERS or {},
    )


async def main(terminal_mode: bool = False) -> None:
    init_observability(cfg.export_config(mask_sensitive=False))
    #   
    logger.remove()
    logger.add(
        sys.stderr,
        level="DEBUG",
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}"
    )
    logger.add(loguru_sink, level="TRACE", enqueue=False, backtrace=False, diagnose=False)

    logger.info(" Eve ...")

    #   
    workspace = cfg.resolve_workspace_dir("default")
    template_workspace = (Path(__file__).resolve().parent / "workspace").resolve()
    if workspace.resolve() == template_workspace:
        fallback_workspace = cfg.resolve_default_workspace_dir().resolve()
        logger.warning(
            "[workspace] configured workspace points to template dir; "
            f"fallback to user workspace: {fallback_workspace}"
        )
        workspace = fallback_workspace
    bootstrap_workspace_from_template(
        workspace_dir=workspace,
        template_dir=template_workspace,
    )
    sessions_dir = ensure_dir(cfg.SESSIONS_DIR)
    data_dir = ensure_dir(cfg.resolve_state_dir())
    ensure_dir(workspace / "memory")

    #  
    pid_file = data_dir / "auraeve.pid"
    if pid_file.exists():
        old_pid = pid_file.read_text().strip()
        if old_pid.isdigit():
            current_pid = os.getpid()
            if int(old_pid) == current_pid:
                # Common in containers where PID 1 is reused across restarts.
                pass
            else:
                try:
                    os.kill(int(old_pid), 0)  # ?0 ?
                    logger.error(
                        f"Detected running auraeve process (PID {old_pid}); refusing to start. "
                        f"Kill it first: kill {old_pid}"
                    )
                    sys.exit(1)
                except (OSError, ProcessLookupError):
                    pass  # PID 

    #   
    bus = MessageBus()
    provider = _build_provider()
    stt_runtime = build_runtime_from_config(cfg.export_config(mask_sensitive=False))
    media_runtime = build_media_runtime_from_config(
        config=cfg.export_config(mask_sensitive=False),
        workspace=workspace,
        stt_runtime=stt_runtime,
        llm_provider=provider,
    )
    execution_workspace = str(workspace.expanduser().resolve())

    #  ?
    memory_file_change_notifier = None
    engine_type = getattr(cfg, "CONTEXT_ENGINE", "vector")
    if engine_type == "vector":
        from auraeve.agent.engines.vector.engine import VectorContextEngine
        embedder = _OpenAIEmbedder(
            api_key=getattr(cfg, "EMBEDDING_API_KEY", cfg.LLM_API_KEY),
            api_base=getattr(cfg, "EMBEDDING_API_BASE", None),
            model=getattr(cfg, "EMBEDDING_MODEL", "text-embedding-3-small"),
        )
        engine = VectorContextEngine(
            workspace=workspace,
            db_path=getattr(cfg, "VECTOR_DB_PATH", cfg.resolve_vector_db_path()),
            embedder=embedder,
            provider=provider,
            token_budget=getattr(cfg, "TOKEN_BUDGET", 120_000),
            compact_threshold=getattr(cfg, "COMPACTION_THRESHOLD_RATIO", 0.85),
            search_limit=getattr(cfg, "MEMORY_SEARCH_LIMIT", 8),
            vector_weight=getattr(cfg, "MEMORY_VECTOR_WEIGHT", 0.7),
            text_weight=getattr(cfg, "MEMORY_TEXT_WEIGHT", 0.3),
            mmr_lambda=getattr(cfg, "MEMORY_MMR_LAMBDA", 0.7),
            half_life_days=getattr(cfg, "MEMORY_TEMPORAL_HALF_LIFE_DAYS", 30.0),
            sessions_dir=sessions_dir,
            include_sessions=bool(getattr(cfg, "MEMORY_INCLUDE_SESSIONS", False)),
            sessions_max_messages=int(getattr(cfg, "MEMORY_SESSIONS_MAX_MESSAGES", 400)),
            execution_workspace=execution_workspace,
        )
        await engine.bootstrap()
        memory_file_change_notifier = engine.memory_manager.mark_dirty
    else:
        from auraeve.agent.engines.legacy import LegacyContextEngine
        engine = LegacyContextEngine(
            workspace=workspace,
            memory_window=getattr(cfg, "LLM_MEMORY_WINDOW", 50),
            execution_workspace=execution_workspace,
        )

    #  Cron  
    cron_store_path = cfg.resolve_cron_store_path()
    ensure_dir(cron_store_path.parent)
    cron_service = CronService(store_path=cron_store_path)

    #  ?
    plugin_settings = merge_plugin_settings_from_config(
        {
            "PLUGINS_ENABLED": getattr(cfg, "PLUGINS_ENABLED", True),
            "PLUGINS_ALLOW": getattr(cfg, "PLUGINS_ALLOW", []),
            "PLUGINS_DENY": getattr(cfg, "PLUGINS_DENY", []),
            "PLUGINS_LOAD_PATHS": getattr(cfg, "PLUGINS_LOAD_PATHS", []),
            "PLUGINS_ENTRIES": getattr(cfg, "PLUGINS_ENTRIES", {}),
        }
    )
    plugin_registry = PluginRegistry()
    plugin_registry.register_discovered(
        workspace=workspace,
        auto_discovery_enabled=getattr(cfg, "PLUGINS_AUTO_DISCOVERY_ENABLED", True),
        enabled=plugin_settings.enabled,
        allow=plugin_settings.allow,
        deny=plugin_settings.deny,
        load_paths=plugin_settings.load_paths,
        entries=plugin_settings.entries,
    )
    # ?
    # from myapp.plugins import MyPlugin
    # plugin_registry.register(MyPlugin())

    #  IdentityService + Resolver
    from auraeve.identity.store import IdentityStore
    from auraeve.identity.service import IdentityService
    from auraeve.identity.resolver import IdentityResolver

    identity_db = data_dir / "identity.db"
    identity_store = IdentityStore(identity_db)
    identity_service = IdentityService(identity_store)
    identity_resolver = IdentityResolver(identity_service)

    #  owner ?canonical ?
    owner_qq = getattr(cfg, "NAPCAT_OWNER_QQ", None) or getattr(cfg, "OWNER_QQ", None)
    owner_canonical_id: str | None = None
    if owner_qq:
        owner_binding = identity_service.resolve_or_create("napcat", str(owner_qq))
        owner_canonical_id = owner_binding.canonical_user_id
        existing_rel = identity_service.get_relationship(owner_binding.canonical_user_id)
        if not existing_rel:
            identity_service.set_relationship(
                canonical_user_id=owner_binding.canonical_user_id,
                relationship="brother",
                source="config",
            )
            logger.info(f"[identity] ?owner QQ {owner_qq} ??{owner_binding.canonical_user_id}")

    webui_owner_user_id = getattr(cfg, "WEBUI_OWNER_USER_ID", "").strip()
    if owner_canonical_id and webui_owner_user_id:
        identity_service.bind(
            channel="webui",
            external_user_id=webui_owner_user_id,
            canonical_user_id=owner_canonical_id,
            confidence=1.0,
        )
        logger.info(
            f"[identity] ?WebUI  {webui_owner_user_id} ?owner canonical {owner_canonical_id}"
        )

    #  RuntimeKernel 
    agent = RuntimeKernel(
        bus=bus,
        provider=provider,
        media_runtime=media_runtime,
        workspace=workspace,
        sessions_dir=sessions_dir,
        engine=engine,
        model=cfg.LLM_MODEL,
        temperature=cfg.LLM_TEMPERATURE,
        max_tokens=cfg.LLM_MAX_TOKENS,
        max_iterations=cfg.LLM_MAX_TOOL_ITERATIONS,
        runtime_execution=getattr(cfg, "RUNTIME_EXECUTION", None),
        runtime_loop_guard=getattr(cfg, "RUNTIME_LOOP_GUARD", None),
        brave_api_key=cfg.BRAVE_API_KEY or None,
        exec_timeout=cfg.EXEC_TIMEOUT,
        restrict_to_workspace=cfg.RESTRICT_TO_WORKSPACE,
        mcp_config=getattr(cfg, "MCP", {}),
        cron_service=cron_service,
        channel_users=getattr(cfg, "CHANNEL_USERS", {}),
        notify_channel=getattr(cfg, "NOTIFY_CHANNEL", ""),
        thinking_budget_tokens=getattr(cfg, "LLM_THINKING_BUDGET_TOKENS", 0) or None,
        plugin_registry=plugin_registry,
        token_budget=getattr(cfg, "TOKEN_BUDGET", 120_000),
        global_deny_tools=set(getattr(cfg, "GLOBAL_DENY_TOOLS", []) or []),
        session_tool_policy=getattr(cfg, "SESSION_TOOL_POLICY", {}) or {},
        max_global_subagent_concurrent=getattr(cfg, "MAX_GLOBAL_SUBAGENT_CONCURRENT", 10),
        max_session_subagent_concurrent=getattr(cfg, "MAX_SESSION_SUBAGENT_CONCURRENT", 3),
        identity_resolver=identity_resolver,
        execution_workspace=execution_workspace,
        memory_lifecycle=MemoryLifecycleService(
            workspace=workspace,
            provider=provider,
            model=cfg.LLM_MODEL,
            timezone=os.getenv("AURAEVE_TIMEZONE") or os.getenv("TZ") or "Asia/Shanghai",
            on_memory_file_changed=memory_file_change_notifier,
        ),
    )

    # ?Cron ?on_job ?agent
    async def _on_cron_job(job):
        from auraeve.bus.events import OutboundMessage
        response = await agent.process_direct(
            content=job.payload.message,
            session_key=f"cron:{job.id}",
            channel="cron",
            chat_id=job.id,
        )
        if job.payload.deliver and job.payload.channel and job.payload.to and response:
            await bus.publish_outbound(OutboundMessage(
                channel=job.payload.channel,
                chat_id=job.payload.to,
                content=response,
            ))
        return response

    cron_service.on_job = _on_cron_job

    #  Heartbeat  
    heartbeat = HeartbeatService(
        workspace=workspace,
        on_heartbeat=lambda prompt: agent.process_direct(
            content=prompt,
            session_key="heartbeat:main",
            channel="heartbeat",
            chat_id="main",
        ),
        interval_s=cfg.HEARTBEAT_INTERVAL_S,
        enabled=cfg.HEARTBEAT_ENABLED,
    )

    #  
    channels = []
    channel_tasks: dict[str, asyncio.Task] = {}
    dingtalk_channel: DingTalkChannel | None = None
    napcat_channel: NapCatChannel | None = None

    def _is_dingtalk_configured() -> bool:
        return bool(
            getattr(cfg, "DINGTALK_ENABLED", True)
            and getattr(cfg, "DINGTALK_CLIENT_ID", "")
            and getattr(cfg, "DINGTALK_CLIENT_SECRET", "")
            and cfg.DINGTALK_CLIENT_ID not in ("", "your-app-key")
            and cfg.DINGTALK_CLIENT_SECRET not in ("", "your-app-secret")
        )

    def _remove_channel_task(name: str) -> None:
        task = channel_tasks.pop(name, None)
        if task and not task.done():
            task.cancel()

    def _remove_channel_from_list(target) -> None:
        nonlocal channels
        channels = [ch for ch in channels if ch is not target]

    def _remove_napcat_tools() -> None:
        for name in list(agent.tools.tool_names):
            if name.startswith("napcat_"):
                agent.tools.unregister(name)

    async def _start_dingtalk_channel() -> bool:
        nonlocal dingtalk_channel
        if dingtalk_channel is not None:
            return True
        if not _is_dingtalk_configured():
            return False
        dingtalk_cfg = DingTalkConfig(
            client_id=cfg.DINGTALK_CLIENT_ID,
            client_secret=cfg.DINGTALK_CLIENT_SECRET,
            allow_from=cfg.DINGTALK_ALLOW_FROM,
        )
        ch = DingTalkChannel(
            dingtalk_cfg,
            bus,
            workspace=workspace,
        )
        dingtalk_channel = ch
        bus.subscribe_outbound("dingtalk", ch.send)
        channels.append(ch)
        channel_tasks["dingtalk"] = asyncio.create_task(ch.start())
        logger.info("Channel: DingTalk started")
        return True

    async def _stop_dingtalk_channel() -> None:
        nonlocal dingtalk_channel
        if dingtalk_channel is None:
            return
        ch = dingtalk_channel
        dingtalk_channel = None
        _remove_channel_task("dingtalk")
        bus.unsubscribe_outbound("dingtalk", ch.send)
        await ch.stop()
        _remove_channel_from_list(ch)
        logger.info("Channel: DingTalk stopped")

    async def _restart_dingtalk_channel() -> bool:
        await _stop_dingtalk_channel()
        return await _start_dingtalk_channel()

    async def _start_napcat_channel() -> bool:
        nonlocal napcat_channel
        if napcat_channel is not None:
            return True
        if not getattr(cfg, "NAPCAT_ENABLED", False):
            return False
        napcat_cfg = NapCatConfig(
            ws_url=getattr(cfg, "NAPCAT_WS_URL", "ws://127.0.0.1:3001"),
            access_token=getattr(cfg, "NAPCAT_ACCESS_TOKEN", ""),
            owner_qq=getattr(cfg, "NAPCAT_OWNER_QQ", ""),
            allow_from=getattr(cfg, "NAPCAT_ALLOW_FROM", []),
            allow_groups=getattr(cfg, "NAPCAT_ALLOW_GROUPS", []),
        )
        ch = NapCatChannel(napcat_cfg, bus)
        napcat_channel = ch
        bus.subscribe_outbound("napcat", ch.send)
        agent.register_channel_sender("napcat", ch.send)
        channels.append(ch)
        channel_tasks["napcat"] = asyncio.create_task(ch.start())
        from auraeve.agent.tools.napcat import create_napcat_tools
        napcat_media_dir = workspace / "media"
        _remove_napcat_tools()
        for t in create_napcat_tools(ch._call_action, friend_flags=ch._friend_flags, media_dir=napcat_media_dir):
            agent.register_tool(t)
        logger.info(f"Channel: NapCat/QQ ({napcat_cfg.ws_url})")
        return True

    async def _stop_napcat_channel() -> None:
        nonlocal napcat_channel
        if napcat_channel is None:
            _remove_napcat_tools()
            return
        ch = napcat_channel
        napcat_channel = None
        _remove_channel_task("napcat")
        bus.unsubscribe_outbound("napcat", ch.send)
        message_tool = agent.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool._direct_senders.pop("napcat", None)
        _remove_napcat_tools()
        await ch.stop()
        _remove_channel_from_list(ch)
        logger.info("Channel: NapCat stopped")

    async def _restart_napcat_channel() -> bool:
        await _stop_napcat_channel()
        return await _start_napcat_channel()

    if terminal_mode:
        terminal_channel = TerminalChannel(TerminalConfig(), bus)
        bus.subscribe_outbound("terminal", terminal_channel.send)
        channels.append(terminal_channel)
        logger.info(": ")

    if _is_dingtalk_configured():
        await _start_dingtalk_channel()

    if getattr(cfg, "NAPCAT_ENABLED", False):
        await _start_napcat_channel()

    if not channels:
        logger.warning("")
        terminal_channel = TerminalChannel(TerminalConfig(), bus)
        bus.subscribe_outbound("terminal", terminal_channel.send)
        channels.append(terminal_channel)

    #  WebUI 
    webui_server: WebUIServer | None = None
    webui_channel: WebUIChannel | None = None
    if getattr(cfg, "WEBUI_ENABLED", False):
        webui_bind_port_raw = str(os.getenv("AURAEVE_WEBUI_BIND_PORT", "")).strip()
        webui_bind_port = int(webui_bind_port_raw) if webui_bind_port_raw else int(getattr(cfg, "WEBUI_PORT", 8080))
        chat_svc = ChatService(
            session_manager=agent.sessions,
            bus=bus,
        )

        async def _on_runtime_apply(new_config: dict, hot_keys: list[str]) -> dict:
            nonlocal plugin_registry

            if not getattr(cfg, "RUNTIME_HOT_APPLY_ENABLED", True):
                return {"applied": [], "requiresRestart": list(hot_keys), "issues": []}

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
                "NAPCAT_OWNER_QQ",
                "CHANNEL_USERS",
                "NOTIFY_CHANNEL",
            }
            STT_KEYS = {
                "STT_ENABLED",
                "STT_DEFAULT_LANGUAGE",
                "STT_TIMEOUT_MS",
                "STT_MAX_CONCURRENCY",
                "STT_RETRY_COUNT",
                "STT_FAILOVER_ENABLED",
                "STT_CACHE_ENABLED",
                "STT_CACHE_TTL_S",
                "STT_PROVIDERS",
            }
            MEDIA_KEYS = {"MEDIA_UNDERSTANDING"}
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

            applied: set[str] = set()
            restart: set[str] = set()
            issues: list[dict[str, str]] = []
            remaining = set(hot_keys)

            def _merge_runtime_result(result: dict) -> None:
                applied.update(result.get("applied") or [])
                restart.update(result.get("requiresRestart") or [])
                runtime_issues = result.get("issues") or []
                if isinstance(runtime_issues, list):
                    for item in runtime_issues:
                        if isinstance(item, dict):
                            issues.append(item)

            core_patch = {
                key: new_config[key]
                for key in remaining
                if key in CORE_RUNTIME_KEYS and key in new_config
            }
            if core_patch:
                _merge_runtime_result(await agent.reload_runtime_config(core_patch))
                remaining -= set(core_patch.keys())

            heartbeat_patch = {
                key: new_config[key]
                for key in remaining
                if key in HEARTBEAT_KEYS and key in new_config
            }
            if heartbeat_patch:
                if "HEARTBEAT_INTERVAL_S" in heartbeat_patch:
                    heartbeat.interval_s = int(heartbeat_patch["HEARTBEAT_INTERVAL_S"])
                    applied.add("HEARTBEAT_INTERVAL_S")
                if "HEARTBEAT_ENABLED" in heartbeat_patch:
                    desired_enabled = bool(heartbeat_patch["HEARTBEAT_ENABLED"])
                    heartbeat.enabled = desired_enabled
                    if desired_enabled and not getattr(heartbeat, "_running", False):
                        await heartbeat.start()
                    if not desired_enabled and getattr(heartbeat, "_running", False):
                        heartbeat.stop()
                    applied.add("HEARTBEAT_ENABLED")
                remaining -= set(heartbeat_patch.keys())

            if "MCP" in remaining and "MCP" in new_config:
                _merge_runtime_result(await agent.reload_runtime_config({"MCP": new_config["MCP"]}))
                remaining.discard("MCP")

            stt_patch_keys = {key for key in remaining if key in STT_KEYS}
            if stt_patch_keys:
                try:
                    stt_runtime.reload(
                        runtime_config_from_dict(cfg.export_config(mask_sensitive=False))
                    )
                    applied.update(stt_patch_keys)
                except Exception as exc:
                    restart.update(stt_patch_keys)
                    issues.append({"code": "stt_hot_reload_failed", "message": str(exc)})
                remaining -= stt_patch_keys

            media_patch_keys = {key for key in remaining if key in MEDIA_KEYS}
            if media_patch_keys:
                try:
                    media_runtime.reload_config(cfg.export_config(mask_sensitive=False))
                    applied.update(media_patch_keys)
                except Exception as exc:
                    restart.update(media_patch_keys)
                    issues.append({"code": "media_hot_reload_failed", "message": str(exc)})
                remaining -= media_patch_keys

            channel_patch_keys = {key for key in remaining if key in CHANNEL_KEYS}
            if channel_patch_keys:
                dingtalk_restart_keys = {
                    "DINGTALK_ENABLED",
                    "DINGTALK_CLIENT_ID",
                    "DINGTALK_CLIENT_SECRET",
                }
                napcat_restart_keys = {
                    "NAPCAT_ENABLED",
                    "NAPCAT_WS_URL",
                    "NAPCAT_ACCESS_TOKEN",
                }

                if channel_patch_keys & dingtalk_restart_keys:
                    try:
                        if _is_dingtalk_configured():
                            started = await _restart_dingtalk_channel()
                            if started:
                                applied.update(channel_patch_keys & dingtalk_restart_keys)
                            else:
                                restart.update(channel_patch_keys & dingtalk_restart_keys)
                        else:
                            await _stop_dingtalk_channel()
                            applied.update(channel_patch_keys & dingtalk_restart_keys)
                    except Exception as exc:
                        restart.update(channel_patch_keys & dingtalk_restart_keys)
                        issues.append({"code": "dingtalk_hot_reload_failed", "message": str(exc)})

                if channel_patch_keys & napcat_restart_keys:
                    try:
                        if getattr(cfg, "NAPCAT_ENABLED", False):
                            started = await _restart_napcat_channel()
                            if started:
                                applied.update(channel_patch_keys & napcat_restart_keys)
                            else:
                                restart.update(channel_patch_keys & napcat_restart_keys)
                        else:
                            await _stop_napcat_channel()
                            applied.update(channel_patch_keys & napcat_restart_keys)
                    except Exception as exc:
                        restart.update(channel_patch_keys & napcat_restart_keys)
                        issues.append({"code": "napcat_hot_reload_failed", "message": str(exc)})

                for key in channel_patch_keys:
                    if key in dingtalk_restart_keys or key in napcat_restart_keys:
                        continue
                    if key == "DINGTALK_ALLOW_FROM":
                        if dingtalk_channel is None:
                            restart.add(key)
                            issues.append({"code": "channel_not_running", "message": "dingtalk channel is not running"})
                        else:
                            dingtalk_channel.config.allow_from = list(new_config.get(key) or [])
                            applied.add(key)
                    elif key == "NAPCAT_ALLOW_FROM":
                        if napcat_channel is None:
                            restart.add(key)
                            issues.append({"code": "channel_not_running", "message": "napcat channel is not running"})
                        else:
                            napcat_channel.config.allow_from = list(new_config.get(key) or [])
                            applied.add(key)
                    elif key == "NAPCAT_ALLOW_GROUPS":
                        if napcat_channel is None:
                            restart.add(key)
                            issues.append({"code": "channel_not_running", "message": "napcat channel is not running"})
                        else:
                            napcat_channel.config.allow_groups = list(new_config.get(key) or [])
                            applied.add(key)
                    elif key == "NAPCAT_OWNER_QQ":
                        if napcat_channel is None:
                            restart.add(key)
                            issues.append({"code": "channel_not_running", "message": "napcat channel is not running"})
                        else:
                            napcat_channel.config.owner_qq = str(new_config.get(key) or "")
                            applied.add(key)
                    elif key == "CHANNEL_USERS":
                        channel_users = dict(new_config.get(key) or {})
                        agent._channel_users = channel_users
                        message_tool = agent.tools.get("message")
                        if isinstance(message_tool, MessageTool):
                            message_tool._channel_users = channel_users
                        applied.add(key)
                    elif key == "NOTIFY_CHANNEL":
                        notify_channel = str(new_config.get(key) or "")
                        agent._notify_channel = notify_channel
                        message_tool = agent.tools.get("message")
                        if isinstance(message_tool, MessageTool):
                            message_tool._notify_channel = notify_channel
                        applied.add(key)
                remaining -= channel_patch_keys

            plugin_patch_keys = {key for key in remaining if key in PLUGIN_KEYS}
            if plugin_patch_keys:
                try:
                    plugin_settings_next = merge_plugin_settings_from_config(
                        {
                            "PLUGINS_ENABLED": getattr(cfg, "PLUGINS_ENABLED", True),
                            "PLUGINS_ALLOW": getattr(cfg, "PLUGINS_ALLOW", []),
                            "PLUGINS_DENY": getattr(cfg, "PLUGINS_DENY", []),
                            "PLUGINS_LOAD_PATHS": getattr(cfg, "PLUGINS_LOAD_PATHS", []),
                            "PLUGINS_ENTRIES": getattr(cfg, "PLUGINS_ENTRIES", {}),
                        }
                    )
                    next_registry = PluginRegistry()
                    next_registry.register_discovered(
                        workspace=workspace,
                        auto_discovery_enabled=getattr(cfg, "PLUGINS_AUTO_DISCOVERY_ENABLED", True),
                        enabled=plugin_settings_next.enabled,
                        allow=plugin_settings_next.allow,
                        deny=plugin_settings_next.deny,
                        load_paths=plugin_settings_next.load_paths,
                        entries=plugin_settings_next.entries,
                    )
                    plugin_registry = next_registry
                    hooks = plugin_registry.build_hook_runner()
                    agent.hooks = hooks
                    agent.assembler._hooks = hooks
                    agent._runner._hooks = hooks
                    agent._governor._hooks = hooks
                    applied.update(plugin_patch_keys)
                except Exception as exc:
                    restart.update(plugin_patch_keys)
                    issues.append({"code": "plugins_hot_reload_failed", "message": str(exc)})
                remaining -= plugin_patch_keys

            skill_patch_keys = {key for key in remaining if key in SKILL_KEYS}
            if skill_patch_keys:
                try:
                    context_builder = None
                    if hasattr(engine, "_builder"):
                        context_builder = getattr(engine, "_builder")
                    elif hasattr(engine, "_context_builder"):
                        context_builder = getattr(engine, "_context_builder")
                    if context_builder is not None and hasattr(context_builder, "skills"):
                        skills_loader = getattr(context_builder, "skills")
                        if hasattr(skills_loader, "max_skills_in_prompt"):
                            skills_loader.max_skills_in_prompt = int(getattr(cfg, "SKILLS_LIMIT_MAX_IN_PROMPT", 150))
                        if hasattr(skills_loader, "max_skills_prompt_chars"):
                            skills_loader.max_skills_prompt_chars = int(getattr(cfg, "SKILLS_LIMIT_MAX_PROMPT_CHARS", 30000))
                        if hasattr(skills_loader, "max_skill_file_bytes"):
                            skills_loader.max_skill_file_bytes = int(getattr(cfg, "SKILLS_LIMIT_MAX_FILE_BYTES", 256000))
                        if hasattr(skills_loader, "invalidate_cache"):
                            skills_loader.invalidate_cache()
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

        config_svc = ConfigService(on_runtime_apply=_on_runtime_apply)
        static_dir = Path(__file__).parent / "webui" / "dist"
        webui_server = WebUIServer(
            chat_service=chat_svc,
            config_service=config_svc,
            host=getattr(cfg, "WEBUI_HOST", "0.0.0.0"),
            port=webui_bind_port,
            token=getattr(cfg, "WEBUI_TOKEN", ""),
            static_dir=static_dir if static_dir.exists() else None,
            workspace=workspace,
            mcp_status_provider=agent.get_mcp_status,
            mcp_events_provider=agent.get_mcp_events,
            mcp_reconnect_provider=agent.reconnect_mcp_server,
        )
        webui_channel = WebUIChannel(WebUIChannelConfig(), bus, chat_svc)
        bus.subscribe_outbound("webui", webui_channel.send)
        logger.info(f"WebUIttp://{getattr(cfg, 'WEBUI_HOST', '0.0.0.0')}:{webui_bind_port}")

    # 子体 WebSocket 服务
    subagent_ws_server = None
    if getattr(cfg, "NODE_ENABLED", False):
        from auraeve.subagents.transport.auth import TokenAuth
        from auraeve.subagents.transport.ws_server import SubAgentWSServer

        subagent_auth = TokenAuth()
        node_tokens_v2: dict = getattr(cfg, "NODE_TOKENS", {})
        for nid, info in node_tokens_v2.items():
            subagent_auth.add_token(nid, info["token"])

        subagent_ws_port = getattr(cfg, "SUBAGENT_WS_PORT", 9800)
        subagent_ws_server = SubAgentWSServer(
            orchestrator=agent._task_orchestrator,
            auth=subagent_auth,
            host=getattr(cfg, "NODE_HOST", "0.0.0.0"),
            port=subagent_ws_port,
        )
        logger.info(f"SubAgent WS service: ws://0.0.0.0:{subagent_ws_port}")

    #   PID
    pid_file.write_text(str(os.getpid()))

    #  ?/  
    event_loop = asyncio.get_running_loop()
    _restart_flag = False

    async def _shutdown(restart: bool = False):
        nonlocal _restart_flag
        _restart_flag = restart
        action = "" if restart else ""
        logger.info(f"{action}...")
        agent.stop()
        cron_service.stop()
        heartbeat.stop()

    def _on_sigterm():
        asyncio.create_task(_shutdown(restart=False))

    def _on_sigusr1():
        logger.info(" SIGUSR1?..")
        asyncio.create_task(_shutdown(restart=True))

    for sig, handler in (
        (signal.SIGINT,  lambda: asyncio.create_task(_shutdown(restart=False))),
        (signal.SIGTERM, _on_sigterm),
    ):
        try:
            event_loop.add_signal_handler(sig, handler)
        except NotImplementedError:
            pass

    # SIGUSR1?Unix?
    if hasattr(signal, "SIGUSR1"):
        try:
            event_loop.add_signal_handler(signal.SIGUSR1, _on_sigusr1)
        except NotImplementedError:
            pass

    logger.info(f"    : {cfg.LLM_MODEL}")
    logger.info(f"API     : {cfg.LLM_API_BASE or ' (OpenAI)'}")
    logger.info(f"? : {workspace}")
    logger.info(f": {sessions_dir}")

    #  cron ?heartbeat?
    await cron_service.start()
    await heartbeat.start()
    if agent.memory_lifecycle is not None:
        await agent.memory_lifecycle.start()

    logger.info(f"?{len(channels)} ?..")
    try:
        for ch in channels:
            if ch.name in channel_tasks:
                continue
            channel_tasks[ch.name] = asyncio.create_task(ch.start())

        tasks = [
            agent.run(),
            bus.dispatch_outbound(),
            *channel_tasks.values(),
        ]
        if subagent_ws_server:
            tasks.append(subagent_ws_server.start())
        if webui_server:
            tasks.append(webui_server.start())
        if webui_channel:
            tasks.append(webui_channel.start())
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("?..")
    finally:
        cron_service.stop()
        heartbeat.stop()
        if agent.memory_lifecycle is not None:
            await agent.memory_lifecycle.stop()
        if engine_type == "vector" and hasattr(engine, "memory_manager"):
            await engine.memory_manager.close()
        await agent.close_mcp()
        for task in list(channel_tasks.values()):
            if not task.done():
                task.cancel()
        channel_tasks.clear()
        for ch in list(channels):
            await ch.stop()
        if webui_channel:
            await webui_channel.stop()
        if webui_server:
            await webui_server.stop()
        if subagent_ws_server:
            await subagent_ws_server.stop()
        bus.stop()
        pid_file.unlink(missing_ok=True)
        logger.info("auraeve stopped.")

    # SIGUSR1 ?
    if _restart_flag:
        logger.info("...")
        os.execv(sys.executable, [sys.executable] + sys.argv)


if __name__ == "__main__":
    from auraeve.cli.app import main as cli_main

    cli_main()
