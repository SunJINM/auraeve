# auraeve/transports/acp/protocol.py
"""ACP JSON-RPC 2.0 协议消息类型定义。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

JSONRPC_VERSION = "2.0"

# ── JSON-RPC 基础类型 ──────────────────────────────────────────────────────────

@dataclass
class JsonRpcRequest:
    id: str | int
    method: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"jsonrpc": JSONRPC_VERSION, "id": self.id, "method": self.method, "params": self.params}


@dataclass
class JsonRpcResponse:
    id: str | int | None
    result: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {"jsonrpc": JSONRPC_VERSION, "id": self.id, "result": self.result}


@dataclass
class JsonRpcError:
    id: str | int | None
    code: int
    message: str
    data: Any = None

    def to_dict(self) -> dict[str, Any]:
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            err["data"] = self.data
        return {"jsonrpc": JSONRPC_VERSION, "id": self.id, "error": err}


@dataclass
class JsonRpcNotification:
    method: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"jsonrpc": JSONRPC_VERSION, "method": self.method, "params": self.params}


def parse_jsonrpc(raw: str) -> JsonRpcRequest | JsonRpcNotification | JsonRpcError:
    """将 JSON 字符串解析为 JSON-RPC 消息，解析失败返回 JsonRpcError。"""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return JsonRpcError(id=None, code=-32700, message=f"Parse error: {exc}")
    if not isinstance(data, dict):
        return JsonRpcError(id=None, code=-32600, message="Invalid Request: not an object")
    if data.get("jsonrpc") != "2.0":
        return JsonRpcError(id=data.get("id"), code=-32600, message="Invalid Request: jsonrpc must be '2.0'")
    raw_id = data.get("id")
    if "id" in data and not isinstance(raw_id, (str, int, type(None))):
        return JsonRpcError(id=None, code=-32600, message="Invalid Request: id must be string, number, or null")
    method = data.get("method")
    if not isinstance(method, str):
        return JsonRpcError(id=data.get("id"), code=-32600, message="Invalid Request: missing method")
    params = data.get("params", {})
    if not isinstance(params, dict):
        return JsonRpcError(id=data.get("id"), code=-32600, message="Invalid Request: params must be an object")
    if "id" in data:
        return JsonRpcRequest(id=raw_id, method=method, params=params)
    return JsonRpcNotification(method=method, params=params)


# ── ACP 方法参数与返回值类型 ──────────────────────────────────────────────────

@dataclass
class AcpCapabilities:
    sessionLoad: bool = True
    imagePrompt: bool = False
    embeddedContext: bool = False
    mcp: bool = True


@dataclass
class InitializeParams:
    protocolVersion: str
    agentId: str = "main"
    cwd: str | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)


@dataclass
class InitializeResult:
    protocolVersion: str = "1.0"
    agentId: str = "main"
    capabilities: AcpCapabilities = field(default_factory=AcpCapabilities)

    def to_dict(self) -> dict[str, Any]:
        caps = self.capabilities
        return {
            "protocolVersion": self.protocolVersion,
            "agentId": self.agentId,
            "capabilities": {
                "sessionLoad": caps.sessionLoad,
                "imagePrompt": caps.imagePrompt,
                "embeddedContext": caps.embeddedContext,
                "mcp": caps.mcp,
            },
        }


@dataclass
class SessionInfo:
    sessionId: str
    sessionKey: str
    state: str = "idle"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessionId": self.sessionId,
            "sessionKey": self.sessionKey,
            "state": self.state,
            "metadata": self.metadata,
        }


@dataclass
class NewSessionParams:
    agentId: str = "main"
    cwd: str | None = None
    mode: str = "persistent"
    backendId: str = "acp"
    label: str = ""


@dataclass
class NewSessionResult:
    session: SessionInfo

    def to_dict(self) -> dict[str, Any]:
        return {"session": self.session.to_dict()}


@dataclass
class LoadSessionParams:
    sessionId: str
    agentId: str = "main"


@dataclass
class LoadSessionResult:
    session: SessionInfo
    loaded: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"session": self.session.to_dict(), "loaded": self.loaded}


@dataclass
class PromptParams:
    sessionId: str
    runId: str
    blocks: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptResult:
    runId: str
    stopReason: str = "stop"

    def to_dict(self) -> dict[str, Any]:
        return {"runId": self.runId, "stopReason": self.stopReason}


@dataclass
class ListSessionsResult:
    sessions: list[SessionInfo] = field(default_factory=list)
    total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"sessions": [s.to_dict() for s in self.sessions], "total": self.total}


@dataclass
class SetSessionModeParams:
    sessionId: str
    mode: str  # adaptive | off | minimal | low | medium | high | xhigh


@dataclass
class SetSessionConfigOptionParams:
    sessionId: str
    key: str   # thought_level | fast_mode | verbose_level | reasoning_level | response_usage | elevated_level
    value: str
