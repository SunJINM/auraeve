from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatHistoryResponse(BaseModel):
    sessionKey: str
    messages: list[dict[str, Any]]


class ChatSendRequest(BaseModel):
    sessionKey: str = Field(min_length=1, max_length=200)
    message: str = Field(default="", max_length=20000)
    idempotencyKey: str = Field(min_length=1, max_length=200)
    userId: str = Field(min_length=1, max_length=200)
    displayName: str | None = Field(default=None, max_length=200)


class ChatSendResponse(BaseModel):
    runId: str
    status: Literal["started", "in_flight"]


class ChatAbortRequest(BaseModel):
    sessionKey: str = Field(min_length=1, max_length=200)
    runId: str | None = None


class ChatAbortResponse(BaseModel):
    ok: bool
    runId: str | None = None
    status: Literal["aborted", "not_found"]


class ConfigGetResponse(BaseModel):
    config: dict[str, Any]
    baseHash: str
    valid: bool = True
    issues: list[dict[str, Any]] = Field(default_factory=list)


class ConfigSchemaField(BaseModel):
    key: str
    type: Literal["string", "number", "boolean", "integer", "object", "array"]
    label: str
    description: str
    sensitive: bool = False
    restartRequired: bool = False


class ConfigSchemaGroup(BaseModel):
    key: str
    title: str
    fields: list[ConfigSchemaField]


class ConfigSchemaResponse(BaseModel):
    version: str = "v1"
    groups: list[ConfigSchemaGroup]


class ConfigWriteRequest(BaseModel):
    baseHash: str = Field(min_length=1)
    config: dict[str, Any] | None = None
    raw: str | None = None


class ConfigWriteResponse(BaseModel):
    ok: bool
    baseHash: str
    changed: list[str] = Field(default_factory=list)
    applied: list[str] = Field(default_factory=list)
    requiresRestart: list[str] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)


class PluginInstallRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    link: bool = False


class PluginEnableRequest(BaseModel):
    id: str = Field(min_length=1, max_length=200)


class PluginUninstallRequest(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    keepFiles: bool = False


class PluginInfoResponse(BaseModel):
    ok: bool
    plugin: dict[str, Any] | None = None
    message: str | None = None


class PluginListResponse(BaseModel):
    ok: bool
    plugins: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None


class PluginActionResponse(BaseModel):
    ok: bool
    message: str | None = None
    id: str | None = None
    installPath: str | None = None
    removedFiles: bool | None = None
    enabled: bool | None = None


class SkillInstallRequest(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    installId: str | None = Field(default=None, max_length=200)


class SkillHubInstallRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=300)
    version: str | None = Field(default=None, max_length=100)
    force: bool = False


class SkillUploadInstallRequest(BaseModel):
    uploadId: str = Field(min_length=1, max_length=128)
    force: bool = False


class SkillEnableRequest(BaseModel):
    id: str = Field(min_length=1, max_length=200)


class SkillSyncRequest(BaseModel):
    all: bool = False
    dryRun: bool = False


class SkillInfoResponse(BaseModel):
    ok: bool
    skill: dict[str, Any] | None = None
    message: str | None = None


class SkillListResponse(BaseModel):
    ok: bool
    skills: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None


class SkillActionResponse(BaseModel):
    ok: bool
    message: str | None = None
    id: str | None = None
    enabled: bool | None = None
    installId: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    installed: list[dict[str, Any]] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    failed: list[dict[str, Any]] = Field(default_factory=list)


class SkillUploadResponse(BaseModel):
    ok: bool
    uploadId: str | None = None
    filename: str | None = None
    size: int | None = None
    sha256: str | None = None
    message: str | None = None


class MCPConfigRequest(BaseModel):
    baseHash: str = Field(min_length=1)
    config: dict[str, Any]


class MCPValidateRequest(BaseModel):
    config: dict[str, Any]


class MCPReconnectRequest(BaseModel):
    serverId: str = Field(min_length=1, max_length=200)


class MCPTestRequest(BaseModel):
    serverId: str = Field(default="draft-server", min_length=1, max_length=200)
    server: dict[str, Any]


class MCPConfigResponse(BaseModel):
    ok: bool
    baseHash: str
    config: dict[str, Any]
    issues: list[dict[str, Any]] = Field(default_factory=list)


class MCPValidateResponse(BaseModel):
    ok: bool
    issues: list[dict[str, Any]] = Field(default_factory=list)


class MCPApplyResponse(BaseModel):
    ok: bool
    baseHash: str
    changed: list[str] = Field(default_factory=list)
    applied: list[str] = Field(default_factory=list)
    requiresRestart: list[str] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)


class MCPStatusResponse(BaseModel):
    ok: bool
    status: dict[str, Any]


class MCPEventsResponse(BaseModel):
    ok: bool
    events: list[dict[str, Any]] = Field(default_factory=list)


class MCPReconnectAllResponse(BaseModel):
    ok: bool
    status: dict[str, Any]
    reconnected: list[str] = Field(default_factory=list)
    failed: list[dict[str, Any]] = Field(default_factory=list)


class MCPTemplatesResponse(BaseModel):
    ok: bool
    templates: list[dict[str, Any]] = Field(default_factory=list)


class MCPTestResponse(BaseModel):
    ok: bool
    issues: list[dict[str, Any]] = Field(default_factory=list)
    status: dict[str, Any] | None = None


class MCPMetricsResponse(BaseModel):
    ok: bool
    metrics: dict[str, Any] = Field(default_factory=dict)


class MCPAuditResponse(BaseModel):
    ok: bool
    records: list[dict[str, Any]] = Field(default_factory=list)


class LogsTailResponse(BaseModel):
    file: str
    cursor: int
    size: int
    events: list[dict[str, Any]] = Field(default_factory=list)
    truncated: bool = False
    reset: bool = False


class LogsSearchRequest(BaseModel):
    levels: list[str] = Field(default_factory=list)
    subsystems: list[str] = Field(default_factory=list)
    kinds: list[str] = Field(default_factory=list)
    text: str | None = Field(default=None, max_length=500)
    sessionKey: str | None = Field(default=None, max_length=200)
    runId: str | None = Field(default=None, max_length=200)
    channel: str | None = Field(default=None, max_length=100)
    fromTs: str | None = None
    toTs: str | None = None
    limit: int = Field(default=200, ge=1, le=5000)
    offset: int = Field(default=0, ge=0, le=200000)


class LogsSearchResponse(BaseModel):
    total: int
    limit: int
    offset: int
    hasMore: bool
    events: list[dict[str, Any]] = Field(default_factory=list)


class LogsStatsResponse(BaseModel):
    total: int
    byLevel: dict[str, int] = Field(default_factory=dict)
    byKind: dict[str, int] = Field(default_factory=dict)
    topSubsystems: list[dict[str, Any]] = Field(default_factory=list)
    topKinds: list[dict[str, Any]] = Field(default_factory=list)
    topChannels: list[dict[str, Any]] = Field(default_factory=list)
    recentErrors: list[dict[str, Any]] = Field(default_factory=list)


class LogsContextResponse(BaseModel):
    ok: bool
    events: list[dict[str, Any]] = Field(default_factory=list)


class LogsExportRequest(BaseModel):
    format: Literal["jsonl", "csv"] = "jsonl"
    levels: list[str] = Field(default_factory=list)
    subsystems: list[str] = Field(default_factory=list)
    kinds: list[str] = Field(default_factory=list)
    text: str | None = Field(default=None, max_length=500)
    sessionKey: str | None = Field(default=None, max_length=200)
    runId: str | None = Field(default=None, max_length=200)
    channel: str | None = Field(default=None, max_length=100)
    fromTs: str | None = None
    toTs: str | None = None
    limit: int = Field(default=5000, ge=1, le=10000)
