from __future__ import annotations

from typing import Any, Awaitable, Callable

import auraeve.config as cfg
from auraeve.agent.tools.registry import ToolRegistry
from auraeve.mcp import MCPRuntimeManager, validate_mcp_config
from auraeve.observability import get_observability
from auraeve.webui.config_service import ConfigService


MCPStatusFn = Callable[[], dict[str, Any]]
MCPEventsFn = Callable[[], list[dict[str, Any]]]
MCPReconnectFn = Callable[[str], Awaitable[dict[str, Any]]]


class MCPWebService:
    def __init__(
        self,
        config_service: ConfigService,
        *,
        get_status: MCPStatusFn,
        get_events: MCPEventsFn,
        reconnect_server: MCPReconnectFn,
    ) -> None:
        self._config = config_service
        self._get_status = get_status
        self._get_events = get_events
        self._reconnect = reconnect_server
        self._templates = self._build_templates()

    def get_config(self) -> dict[str, Any]:
        snapshot = cfg.read_snapshot()
        current = cfg.export_config(mask_sensitive=False).get("MCP") or {}
        issues = validate_mcp_config(current)
        return {
            "ok": len(issues) == 0,
            "baseHash": snapshot.base_hash,
            "config": current,
            "issues": issues,
        }

    def validate(self, config: dict[str, Any]) -> dict[str, Any]:
        issues = validate_mcp_config(config)
        return {
            "ok": len(issues) == 0,
            "issues": issues,
        }

    def set_config(self, base_hash: str, config: dict[str, Any]) -> dict[str, Any]:
        resp = self._config.set(base_hash, {"MCP": config})
        return resp.model_dump()

    async def apply_config(self, base_hash: str, config: dict[str, Any]) -> dict[str, Any]:
        resp = await self._config.apply(base_hash, {"MCP": config})
        return resp.model_dump()

    def status(self) -> dict[str, Any]:
        return {"ok": True, "status": self._get_status()}

    def events(self) -> dict[str, Any]:
        return {"ok": True, "events": self._get_events()}

    async def reconnect(self, server_id: str) -> dict[str, Any]:
        status = await self._reconnect(server_id)
        return {"ok": True, "status": status}

    async def reconnect_all(self) -> dict[str, Any]:
        status = self._get_status()
        servers = status.get("servers") if isinstance(status, dict) else []
        if not isinstance(servers, list):
            servers = []
        reconnected: list[str] = []
        failed: list[dict[str, str]] = []
        for item in servers:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("serverId") or "").strip()
            enabled = bool(item.get("enabled", True))
            if not sid or not enabled:
                continue
            try:
                await self._reconnect(sid)
                reconnected.append(sid)
            except Exception as exc:  # noqa: BLE001
                failed.append({"serverId": sid, "message": str(exc)})
        return {
            "ok": len(failed) == 0,
            "status": self._get_status(),
            "reconnected": reconnected,
            "failed": failed,
        }

    def templates(self) -> dict[str, Any]:
        return {"ok": True, "templates": self._templates}

    async def test_connection(self, server_id: str, server: dict[str, Any]) -> dict[str, Any]:
        sid = (server_id or "").strip() or "draft-server"
        test_cfg = {
            "enabled": True,
            "reloadPolicy": "diff",
            "defaultTimeoutMs": 20000,
            "servers": {
                sid: server,
            },
        }
        issues = validate_mcp_config(test_cfg)
        if issues:
            return {"ok": False, "issues": issues, "status": None}

        registry = ToolRegistry()
        runtime = MCPRuntimeManager(registry, test_cfg)
        try:
            await runtime.start()
            runtime_status = runtime.status()
            target = None
            for item in runtime_status.get("servers", []):
                if isinstance(item, dict) and str(item.get("serverId")) == sid:
                    target = item
                    break
            health = str((target or {}).get("health") or "disconnected")
            return {
                "ok": health == "connected",
                "issues": [] if health == "connected" else [{"path": "MCP.servers", "message": "test connect failed"}],
                "status": target or {"serverId": sid, "health": "disconnected"},
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "issues": [{"path": "MCP.servers", "message": str(exc)}],
                "status": {"serverId": sid, "health": "degraded", "lastError": str(exc)},
            }
        finally:
            await runtime.stop()

    def metrics(self) -> dict[str, Any]:
        events = self._get_events()
        total = len(events)
        connected = 0
        disconnected = 0
        connect_failed = 0
        reload_failed = 0
        by_server: dict[str, dict[str, int]] = {}

        for ev in events:
            if not isinstance(ev, dict):
                continue
            et = str(ev.get("event") or "")
            sid = str(ev.get("serverId") or "").strip()
            if sid and sid not in by_server:
                by_server[sid] = {"connected": 0, "disconnected": 0, "connect_failed": 0}
            if et == "mcp.server.connected":
                connected += 1
                if sid:
                    by_server[sid]["connected"] += 1
            elif et == "mcp.server.disconnected":
                disconnected += 1
                if sid:
                    by_server[sid]["disconnected"] += 1
            elif et == "mcp.server.connect_failed":
                connect_failed += 1
                if sid:
                    by_server[sid]["connect_failed"] += 1
            elif "reload" in et and "failed" in et:
                reload_failed += 1

        ok_events = connected
        fail_events = connect_failed + reload_failed
        success_rate = 100.0 if ok_events + fail_events == 0 else (ok_events * 100.0 / (ok_events + fail_events))
        return {
            "ok": True,
            "metrics": {
                "totalEvents": total,
                "connectedEvents": connected,
                "disconnectedEvents": disconnected,
                "connectFailedEvents": connect_failed,
                "reloadFailedEvents": reload_failed,
                "successRate": round(success_rate, 2),
                "byServer": by_server,
            },
        }

    def audit(self, limit: int = 100) -> dict[str, Any]:
        result = get_observability().search(
            kinds=["audit"],
            subsystems=["config", "mcp"],
            limit=max(1, min(limit, 500)),
            offset=0,
        )
        records: list[dict[str, Any]] = []
        for event in result.get("events", []):
            if not isinstance(event, dict):
                continue
            attrs = event.get("attrs")
            if isinstance(attrs, dict):
                raw_record = attrs.get("record")
                if isinstance(raw_record, dict):
                    records.append(raw_record)
                    continue
            records.append(event)
        return {"ok": True, "records": records}

    @staticmethod
    def _build_templates() -> list[dict[str, Any]]:
        return [
            {
                "templateId": "filesystem",
                "name": "Filesystem Server",
                "description": "Read/write files inside a target directory.",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "./workspace"],
                "requiredEnv": [],
                "recommended": {
                    "toolPrefix": "fs",
                    "retry": {"maxAttempts": 3, "backoffMs": 500},
                    "healthcheck": {"enabled": True, "intervalSec": 60},
                },
            },
            {
                "templateId": "github",
                "name": "GitHub MCP Server",
                "description": "Operate GitHub issues/PRs/repos via token.",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "requiredEnv": ["GITHUB_TOKEN"],
                "recommended": {
                    "toolPrefix": "gh",
                    "retry": {"maxAttempts": 4, "backoffMs": 700},
                    "healthcheck": {"enabled": True, "intervalSec": 60},
                },
            },
            {
                "templateId": "postgres",
                "name": "PostgreSQL MCP Server",
                "description": "Query PostgreSQL with schema-aware SQL tools.",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-postgres"],
                "requiredEnv": ["POSTGRES_CONNECTION_STRING"],
                "recommended": {
                    "toolPrefix": "pg",
                    "retry": {"maxAttempts": 5, "backoffMs": 800},
                    "healthcheck": {"enabled": True, "intervalSec": 45},
                },
            },
            {
                "templateId": "http-remote",
                "name": "Remote HTTP MCP",
                "description": "Connect to a streamable HTTP MCP endpoint.",
                "transport": "http",
                "url": "https://example.com/mcp",
                "requiredEnv": [],
                "recommended": {
                    "toolPrefix": "remote",
                    "retry": {"maxAttempts": 3, "backoffMs": 1000},
                    "healthcheck": {"enabled": True, "intervalSec": 30},
                },
            },
        ]
