from __future__ import annotations

from typing import Any

from .types import MCPConfig, MCPHealthcheckConfig, MCPRetryConfig, MCPServerConfig


class MCPConfigError(ValueError):
    pass


def _as_bool(value: Any, field: str, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise MCPConfigError(f"{field}: expected boolean")


def _as_int(value: Any, field: str, *, default: int, minimum: int = 0) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool):
        raise MCPConfigError(f"{field}: expected integer")
    if value < minimum:
        raise MCPConfigError(f"{field}: expected >= {minimum}")
    return value


def _as_str(value: Any, field: str, *, default: str = "", required: bool = False) -> str:
    if value is None:
        if required:
            raise MCPConfigError(f"{field}: required")
        return default
    if not isinstance(value, str):
        raise MCPConfigError(f"{field}: expected string")
    v = value.strip()
    if required and not v:
        raise MCPConfigError(f"{field}: required")
    return v


def _as_str_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise MCPConfigError(f"{field}: expected array")
    out: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            raise MCPConfigError(f"{field}[{idx}]: expected string")
        out.append(item)
    return out


def _as_str_dict(value: Any, field: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MCPConfigError(f"{field}: expected object")
    out: dict[str, str] = {}
    for k, v in value.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise MCPConfigError(f"{field}: expected string map")
        out[k] = v
    return out


def _normalize_tool_prefix(server_id: str, raw: str) -> str:
    base = raw.strip() or f"mcp_{server_id}"
    chars: list[str] = []
    for ch in base:
        if ch.isalnum() or ch == "_":
            chars.append(ch.lower())
        else:
            chars.append("_")
    normalized = "".join(chars).strip("_")
    return normalized or "mcp"


def _parse_server(server_id: str, raw: Any) -> MCPServerConfig:
    if not isinstance(raw, dict):
        raise MCPConfigError(f"MCP.servers.{server_id}: expected object")
    transport = _as_str(raw.get("transport"), f"MCP.servers.{server_id}.transport", default="stdio")
    if transport not in {"stdio", "http"}:
        raise MCPConfigError(f"MCP.servers.{server_id}.transport: expected one of stdio/http")

    cfg = MCPServerConfig(
        server_id=server_id,
        enabled=_as_bool(raw.get("enabled"), f"MCP.servers.{server_id}.enabled", default=True),
        transport=transport,  # type: ignore[arg-type]
        command=_as_str(raw.get("command"), f"MCP.servers.{server_id}.command"),
        args=_as_str_list(raw.get("args"), f"MCP.servers.{server_id}.args"),
        env=_as_str_dict(raw.get("env"), f"MCP.servers.{server_id}.env"),
        url=_as_str(raw.get("url"), f"MCP.servers.{server_id}.url"),
        headers=_as_str_dict(raw.get("headers"), f"MCP.servers.{server_id}.headers"),
        tool_prefix=_normalize_tool_prefix(
            server_id,
            _as_str(raw.get("toolPrefix"), f"MCP.servers.{server_id}.toolPrefix"),
        ),
        tool_allow=_as_str_list(raw.get("toolAllow"), f"MCP.servers.{server_id}.toolAllow"),
        tool_deny=_as_str_list(raw.get("toolDeny"), f"MCP.servers.{server_id}.toolDeny"),
        retry=MCPRetryConfig(
            max_attempts=_as_int(
                ((raw.get("retry") or {}).get("maxAttempts") if isinstance(raw.get("retry"), dict) else None),
                f"MCP.servers.{server_id}.retry.maxAttempts",
                default=3,
                minimum=1,
            ),
            backoff_ms=_as_int(
                ((raw.get("retry") or {}).get("backoffMs") if isinstance(raw.get("retry"), dict) else None),
                f"MCP.servers.{server_id}.retry.backoffMs",
                default=500,
                minimum=0,
            ),
        ),
        healthcheck=MCPHealthcheckConfig(
            enabled=_as_bool(
                ((raw.get("healthcheck") or {}).get("enabled") if isinstance(raw.get("healthcheck"), dict) else None),
                f"MCP.servers.{server_id}.healthcheck.enabled",
                default=True,
            ),
            interval_sec=_as_int(
                ((raw.get("healthcheck") or {}).get("intervalSec") if isinstance(raw.get("healthcheck"), dict) else None),
                f"MCP.servers.{server_id}.healthcheck.intervalSec",
                default=60,
                minimum=5,
            ),
        ),
    )
    if cfg.transport == "stdio" and not cfg.command:
        raise MCPConfigError(f"MCP.servers.{server_id}.command: required for stdio transport")
    if cfg.transport == "http" and not cfg.url:
        raise MCPConfigError(f"MCP.servers.{server_id}.url: required for http transport")
    return cfg


def parse_mcp_config(raw: Any) -> MCPConfig:
    if raw is None:
        return MCPConfig(enabled=False, servers={})
    if not isinstance(raw, dict):
        raise MCPConfigError("MCP: expected object")
    reload_policy = _as_str(raw.get("reloadPolicy"), "MCP.reloadPolicy", default="diff")
    if reload_policy not in {"none", "full", "diff"}:
        raise MCPConfigError("MCP.reloadPolicy: expected one of none/full/diff")

    servers_raw = raw.get("servers")
    if servers_raw is None:
        servers_raw = {}
    if not isinstance(servers_raw, dict):
        raise MCPConfigError("MCP.servers: expected object")

    servers: dict[str, MCPServerConfig] = {}
    for server_id, server_cfg in servers_raw.items():
        if not isinstance(server_id, str) or not server_id.strip():
            raise MCPConfigError("MCP.servers: server id must be non-empty string")
        sid = server_id.strip()
        servers[sid] = _parse_server(sid, server_cfg)

    return MCPConfig(
        enabled=_as_bool(raw.get("enabled"), "MCP.enabled", default=True),
        reload_policy=reload_policy,  # type: ignore[arg-type]
        default_timeout_ms=_as_int(raw.get("defaultTimeoutMs"), "MCP.defaultTimeoutMs", default=20_000, minimum=100),
        servers=servers,
    )


def validate_mcp_config(raw: Any) -> list[dict[str, str]]:
    try:
        parse_mcp_config(raw)
        return []
    except MCPConfigError as exc:
        return [{"path": "MCP", "message": str(exc)}]

