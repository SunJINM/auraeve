from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ReloadPolicy = Literal["none", "full", "diff"]
TransportType = Literal["stdio", "http"]
ServerHealth = Literal["connected", "disconnected", "degraded"]


@dataclass
class MCPRetryConfig:
    max_attempts: int = 3
    backoff_ms: int = 500


@dataclass
class MCPHealthcheckConfig:
    enabled: bool = True
    interval_sec: int = 60


@dataclass
class MCPServerConfig:
    server_id: str
    enabled: bool = True
    transport: TransportType = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    tool_prefix: str = ""
    tool_allow: list[str] = field(default_factory=list)
    tool_deny: list[str] = field(default_factory=list)
    retry: MCPRetryConfig = field(default_factory=MCPRetryConfig)
    healthcheck: MCPHealthcheckConfig = field(default_factory=MCPHealthcheckConfig)


@dataclass
class MCPConfig:
    enabled: bool = True
    reload_policy: ReloadPolicy = "diff"
    default_timeout_ms: int = 20_000
    servers: dict[str, MCPServerConfig] = field(default_factory=dict)

