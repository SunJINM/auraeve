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
from auraeve.bus.queue import OutboundDispatcher
from auraeve.agent_runtime.kernel import RuntimeKernel
from auraeve.cron.service import CronService
from auraeve.plugins import PluginRegistry
from auraeve.plugins.state import merge_plugin_settings_from_config
from auraeve.heartbeat.service import HEARTBEAT_OK_TOKEN, HeartbeatService
from auraeve.utils.helpers import ensure_dir
from auraeve.channels.webui import WebUIChannel, WebUIChannelConfig
from auraeve.webui.chat_service import ChatService
from auraeve.webui.config_service import ConfigService
from auraeve.webui.server import WebUIServer
from auraeve.stt import build_runtime_from_config
from auraeve.media_understanding import build_media_runtime_from_config
from auraeve.runtime_bootstrap import bootstrap_workspace_from_template
from auraeve.memory_lifecycle import MemoryLifecycleService
from auraeve.runtime_hot_reload import (
    RuntimeHotApplyService,
    sync_message_tool_settings,
)
from auraeve.runtime_channels import ChannelRuntimeManager
from auraeve.runtime_runner import AppRuntimeRunner


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
    logger.remove()
    logger.add(
        sys.stderr,
        level="DEBUG",
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}"
    )
    logger.add(loguru_sink, level="TRACE", enqueue=False, backtrace=False, diagnose=False)

    logger.info(" Eve ...")

    # 工作区与模板区
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
                    os.kill(int(old_pid), 0)
                    logger.error(
                        f"Detected running auraeve process (PID {old_pid}); refusing to start. "
                        f"Kill it first: kill {old_pid}"
                    )
                    sys.exit(1)
                except (OSError, ProcessLookupError):
                    pass  # PID 

    # 消息分发
    bus = OutboundDispatcher()
    provider = _build_provider()
    stt_runtime = build_runtime_from_config(cfg.export_config(mask_sensitive=False))
    media_runtime = build_media_runtime_from_config(
        config=cfg.export_config(mask_sensitive=False),
        workspace=workspace,
        stt_runtime=stt_runtime,
        llm_provider=provider,
    )
    execution_workspace = str(workspace.expanduser().resolve())

    # memory
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

    # Cron
    cron_store_path = cfg.resolve_cron_store_path()
    ensure_dir(cron_store_path.parent)
    cron_service = CronService(store_path=cron_store_path)

    # plugin
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
        max_session_subagent_concurrent=getattr(cfg, "MAX_SESSION_SUBAGENT_CONCURRENT", 8),
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
        agent.command_queue.enqueue_command(
            agent.command_factory(
                session_key=f"cron:{job.id}",
                source="cron",
                mode="cron",
                priority="later",
                payload={
                    "content": job.payload.message,
                    "job_id": job.id,
                    "deliver_channel": job.payload.channel,
                    "deliver_to": job.payload.to,
                },
                origin={"kind": "cron", "is_system_generated": True},
            )
        )
        return None

    async def _enqueue_heartbeat(agent_runtime: RuntimeKernel, prompt: str) -> str:
        agent_runtime.command_queue.enqueue_command(
            agent_runtime.command_factory(
                session_key="heartbeat:main",
                source="heartbeat",
                mode="heartbeat",
                priority="later",
                payload={"content": prompt},
                origin={"kind": "heartbeat", "is_system_generated": True},
            )
        )
        return HEARTBEAT_OK_TOKEN

    cron_service.on_job = _on_cron_job

    #  Heartbeat  
    heartbeat = HeartbeatService(
        workspace=workspace,
        on_heartbeat=lambda prompt: _enqueue_heartbeat(agent, prompt),
        interval_s=cfg.HEARTBEAT_INTERVAL_S,
        enabled=cfg.HEARTBEAT_ENABLED,
    )

    channel_runtime = ChannelRuntimeManager(
        config=cfg,
        bus=bus,
        agent=agent,
        workspace=workspace,
    )
    await channel_runtime.start_initial_channels(terminal_mode=terminal_mode)

    #  WebUI 
    webui_server: WebUIServer | None = None
    webui_channel: WebUIChannel | None = None
    if getattr(cfg, "WEBUI_ENABLED", False):
        webui_bind_port_raw = str(os.getenv("AURAEVE_WEBUI_BIND_PORT", "")).strip()
        webui_bind_port = int(webui_bind_port_raw) if webui_bind_port_raw else int(getattr(cfg, "WEBUI_PORT", 8080))
        chat_svc = ChatService(
            session_manager=agent.sessions,
            command_queue=agent.command_queue,
        )

        hot_apply = RuntimeHotApplyService(
            config=cfg,
            agent=agent,
            heartbeat=heartbeat,
            stt_runtime=stt_runtime,
            media_runtime=media_runtime,
            engine=engine,
            workspace=workspace,
            plugin_registry=plugin_registry,
            plugin_registry_factory=PluginRegistry,
            merge_plugin_settings=merge_plugin_settings_from_config,
            channel_runtime=channel_runtime.build_hot_reload_controls(),
            message_tool_sync=lambda **kwargs: sync_message_tool_settings(agent, **kwargs),
            export_config=lambda: cfg.export_config(mask_sensitive=False),
        )
        config_svc = ConfigService(on_runtime_apply=hot_apply.apply)
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
            restart_callback=None,
            subagent_executor=agent._subagent_executor,
        )
        webui_channel = WebUIChannel(WebUIChannelConfig(), agent.command_queue, chat_svc)
        bus.subscribe_outbound("webui", webui_channel.send)
        logger.info(f"WebUIttp://{getattr(cfg, 'WEBUI_HOST', '0.0.0.0')}:{webui_bind_port}")

    # 子体 WebSocket 服务
    subagent_ws_server = None
    if getattr(cfg, "NODE_ENABLED", False):
        logger.warning("NODE_ENABLED 已废弃，远程子体传输层已在本次重构中移除，忽略该配置。")

    # PID
    pid_file.write_text(str(os.getpid()))

    runtime_runner = AppRuntimeRunner(
        agent=agent,
        cron_service=cron_service,
        heartbeat=heartbeat,
        bus=bus,
        channel_runtime=channel_runtime,
        webui_server=webui_server,
        webui_channel=webui_channel,
        subagent_ws_server=subagent_ws_server,
        pid_file=pid_file,
        on_engine_cleanup=(
            engine.memory_manager.close
            if engine_type == "vector" and hasattr(engine, "memory_manager")
            else None
        ),
    )
    if webui_server is not None:
        webui_server._restart_callback = lambda: runtime_runner.shutdown(restart=True)

    #  ?/  
    event_loop = asyncio.get_running_loop()

    def _on_sigterm():
        asyncio.create_task(runtime_runner.shutdown(restart=False))

    def _on_sigusr1():
        logger.info(" SIGUSR1?..")
        asyncio.create_task(runtime_runner.shutdown(restart=True))

    for sig, handler in (
        (signal.SIGINT,  lambda: asyncio.create_task(runtime_runner.shutdown(restart=False))),
        (signal.SIGTERM, _on_sigterm),
    ):
        try:
            event_loop.add_signal_handler(sig, handler)
        except NotImplementedError:
            # Windows 不支持 add_signal_handler，使用 signal.signal 作为 fallback
            def _win_handler(signum, frame, _h=handler, _loop=event_loop):
                _loop.call_soon_threadsafe(_h)
            signal.signal(sig, _win_handler)

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

    logger.info(f"?{len(channel_runtime.channels)} ?..")
    await runtime_runner.run()

    # SIGUSR1
    if runtime_runner.restart_requested:
        logger.info("...")
        os.execv(sys.executable, [sys.executable] + sys.argv)


if __name__ == "__main__":
    from auraeve.cli.app import main as cli_main

    cli_main()
