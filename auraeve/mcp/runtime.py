from __future__ import annotations

import asyncio
from collections import deque
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from auraeve.observability import get_observability
from auraeve.agent.tools.base import Tool
from auraeve.agent.tools.registry import ToolRegistry

from .config import MCPConfigError, parse_mcp_config
from .types import MCPServerConfig, ServerHealth


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_tool_name(server: MCPServerConfig, original_name: str) -> str:
    name = f"{server.tool_prefix}_{original_name}"
    chars: list[str] = []
    for ch in name:
        if ch.isalnum() or ch == "_":
            chars.append(ch.lower())
        else:
            chars.append("_")
    normalized = "".join(chars).strip("_")
    return normalized or f"{server.tool_prefix}_tool"


def _summarize_tool_result(result: Any) -> str:
    from mcp import types

    parts: list[str] = []
    for block in result.content:
        if isinstance(block, types.TextContent):
            parts.append(block.text)
        else:
            parts.append(str(block))
    return "\n".join(parts) or "（无输出）"


class MCPToolAdapter(Tool):
    def __init__(
        self,
        *,
        session: Any,
        server: MCPServerConfig,
        tool_def: Any,
        tool_name: str,
        timeout_ms: int,
    ) -> None:
        self._session = session
        self._server = server
        self._tool_def = tool_def
        self._tool_name = tool_name
        self._timeout_ms = timeout_ms
        self._description = tool_def.description or tool_def.name
        self._parameters = tool_def.inputSchema or {"type": "object", "properties": {}}

    @property
    def name(self) -> str:
        return self._tool_name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "group": "mcp",
            "mcp": {
                "server_id": self._server.server_id,
                "transport": self._server.transport,
                "tool_name": self._tool_def.name,
                "tool_prefix": self._server.tool_prefix,
            },
        }

    async def execute(self, **kwargs: Any) -> str:
        timeout_s = max(0.1, self._timeout_ms / 1000)
        result = await asyncio.wait_for(
            self._session.call_tool(self._tool_def.name, arguments=kwargs),
            timeout=timeout_s,
        )
        return _summarize_tool_result(result)


@dataclass
class _ServerState:
    cfg: MCPServerConfig
    stack: AsyncExitStack | None = None
    session: Any = None
    tools: list[str] = field(default_factory=list)
    health: ServerHealth = "disconnected"
    last_error: str = ""
    connected_at: str = ""


class MCPRuntimeManager:
    def __init__(self, registry: ToolRegistry, config_raw: Any) -> None:
        self._registry = registry
        self._config = parse_mcp_config(config_raw)
        self._servers: dict[str, _ServerState] = {}
        self._events: deque[dict[str, Any]] = deque(maxlen=500)
        self._lock = asyncio.Lock()

    @staticmethod
    def validate(raw: Any) -> list[dict[str, str]]:
        try:
            parse_mcp_config(raw)
            return []
        except MCPConfigError as exc:
            return [{"path": "MCP", "message": str(exc)}]

    async def start(self) -> None:
        async with self._lock:
            if not self._config.enabled:
                self._emit("mcp.disabled", {})
                return
            for server_id, cfg in self._config.servers.items():
                if not cfg.enabled:
                    continue
                if server_id in self._servers and self._servers[server_id].health == "connected":
                    continue
                await self._connect_server(server_id, cfg)

    async def stop(self) -> None:
        async with self._lock:
            for server_id in list(self._servers.keys()):
                await self._disconnect_server(server_id)

    async def reconnect(self, server_id: str) -> dict[str, Any]:
        async with self._lock:
            cfg = self._config.servers.get(server_id)
            if not cfg:
                raise ValueError(f"unknown mcp server: {server_id}")
            await self._disconnect_server(server_id)
            if cfg.enabled and self._config.enabled:
                await self._connect_server(server_id, cfg)
            return self.status()

    async def reload(self, new_raw: Any) -> dict[str, Any]:
        async with self._lock:
            next_cfg = parse_mcp_config(new_raw)
            applied: list[str] = []
            restart: list[str] = []
            issues: list[dict[str, str]] = []

            if self._config.reload_policy == "none":
                self._config = next_cfg
                return {"applied": [], "requiresRestart": ["MCP"], "issues": []}

            if self._config.reload_policy == "full" or next_cfg.reload_policy == "full":
                try:
                    for server_id in list(self._servers.keys()):
                        await self._disconnect_server(server_id)
                    self._config = next_cfg
                    if self._config.enabled:
                        for sid, scfg in self._config.servers.items():
                            if scfg.enabled:
                                await self._connect_server(sid, scfg)
                    applied.append("MCP")
                except Exception as exc:  # noqa: BLE001
                    restart.append("MCP")
                    issues.append({"code": "mcp_reload_full_failed", "message": str(exc)})
                return {"applied": applied, "requiresRestart": restart, "issues": issues}

            current_ids = set(self._config.servers.keys())
            next_ids = set(next_cfg.servers.keys())
            removed = current_ids - next_ids
            added = next_ids - current_ids
            maybe_changed = current_ids & next_ids

            for sid in removed:
                await self._disconnect_server(sid)

            for sid in maybe_changed:
                if self._config.servers[sid] != next_cfg.servers[sid]:
                    await self._disconnect_server(sid)

            self._config = next_cfg
            try:
                if not self._config.enabled:
                    for sid in list(self._servers.keys()):
                        await self._disconnect_server(sid)
                    applied.append("MCP")
                else:
                    for sid in sorted(
                        sid
                        for sid, scfg in self._config.servers.items()
                        if scfg.enabled and sid not in self._servers
                    ):
                        scfg = self._config.servers[sid]
                        await self._connect_server(sid, scfg)
                    applied.append("MCP")
            except Exception as exc:  # noqa: BLE001
                issues.append({"code": "mcp_reload_diff_failed", "message": str(exc)})
                restart.append("MCP")
            return {"applied": applied, "requiresRestart": restart, "issues": issues}

    def status(self) -> dict[str, Any]:
        servers: list[dict[str, Any]] = []
        for sid, state in self._servers.items():
            servers.append(
                {
                    "serverId": sid,
                    "enabled": state.cfg.enabled,
                    "transport": state.cfg.transport,
                    "health": state.health,
                    "toolCount": len(state.tools),
                    "tools": list(state.tools),
                    "connectedAt": state.connected_at,
                    "lastError": state.last_error or None,
                }
            )
        disconnected = [sid for sid in self._config.servers.keys() if sid not in self._servers]
        for sid in disconnected:
            scfg = self._config.servers[sid]
            servers.append(
                {
                    "serverId": sid,
                    "enabled": scfg.enabled,
                    "transport": scfg.transport,
                    "health": "disconnected",
                    "toolCount": 0,
                    "tools": [],
                    "connectedAt": None,
                    "lastError": None,
                }
            )
        return {
            "enabled": self._config.enabled,
            "reloadPolicy": self._config.reload_policy,
            "defaultTimeoutMs": self._config.default_timeout_ms,
            "servers": sorted(servers, key=lambda x: str(x["serverId"])),
            "events": list(self._events),
        }

    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        entry = {
            "time": _iso_now(),
            "event": event,
            **payload,
        }
        self._events.append(entry)
        get_observability().emit(
            level="info",
            kind="event",
            subsystem="mcp",
            message=event,
            attrs=payload,
        )

    async def _connect_server(self, server_id: str, cfg: MCPServerConfig) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        if server_id in self._servers:
            await self._disconnect_server(server_id)
        attempts = max(1, cfg.retry.max_attempts)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                stack = AsyncExitStack()
                await stack.__aenter__()
                if cfg.transport == "stdio":
                    params = StdioServerParameters(
                        command=cfg.command,
                        args=cfg.args,
                        env=cfg.env or None,
                    )
                    read, write = await stack.enter_async_context(stdio_client(params))
                else:
                    from mcp.client.streamable_http import streamable_http_client

                    read, write, _ = await stack.enter_async_context(streamable_http_client(cfg.url))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                tools = await session.list_tools()

                state = _ServerState(
                    cfg=cfg,
                    stack=stack,
                    session=session,
                    health="connected",
                    connected_at=_iso_now(),
                )
                for tool_def in tools.tools:
                    if cfg.tool_allow and tool_def.name not in set(cfg.tool_allow):
                        continue
                    if cfg.tool_deny and tool_def.name in set(cfg.tool_deny):
                        continue
                    tool_name = _default_tool_name(cfg, tool_def.name)
                    adapter = MCPToolAdapter(
                        session=session,
                        server=cfg,
                        tool_def=tool_def,
                        tool_name=tool_name,
                        timeout_ms=self._config.default_timeout_ms,
                    )
                    self._registry.register(adapter)
                    state.tools.append(tool_name)
                self._servers[server_id] = state
                self._emit(
                    "mcp.server.connected",
                    {"serverId": server_id, "toolCount": len(state.tools)},
                )
                logger.info(
                    f"MCP server connected: {server_id} transport={cfg.transport} tools={len(state.tools)}"
                )
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                wait_s = max(0.0, cfg.retry.backoff_ms / 1000)
                if attempt < attempts and wait_s > 0:
                    await asyncio.sleep(wait_s)
        err = str(last_error) if last_error else "unknown error"
        self._emit("mcp.server.connect_failed", {"serverId": server_id, "error": err})
        logger.error(f"MCP server connect failed: {server_id} error={err}")
        self._servers[server_id] = _ServerState(cfg=cfg, health="degraded", last_error=err)

    async def _disconnect_server(self, server_id: str) -> None:
        state = self._servers.pop(server_id, None)
        if not state:
            return
        for tool_name in state.tools:
            self._registry.unregister(tool_name)
        if state.stack:
            try:
                await state.stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass
        self._emit("mcp.server.disconnected", {"serverId": server_id})
        logger.info(f"MCP server disconnected: {server_id}")
