from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatHistoryResponse(BaseModel):
    sessionKey: str
    messages: list[dict[str, Any]]


class TranscriptUserBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    type: Literal["user"] = "user"
    content: str = ""
    timestamp: str = ""


class TranscriptToolCallBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    type: Literal["tool_call"] = "tool_call"
    toolCallId: str = ""
    toolName: str = ""
    arguments: Any = None


class TranscriptToolResultBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    type: Literal["tool_result"] = "tool_result"
    toolCallId: str = ""
    toolName: str = ""
    content: str = ""


class TranscriptToolUseBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    type: Literal["tool_use"] = "tool_use"
    toolCallId: str = ""
    toolName: str = ""
    arguments: Any = None
    result: str | None = None
    status: Literal["running", "success", "error"] = "running"


class TranscriptAssistantTextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    type: Literal["assistant_text"] = "assistant_text"
    content: str = ""
    timestamp: str = ""


class TranscriptRunStatusBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    type: Literal["run_status"] = "run_status"
    status: Literal["started", "running", "completed", "aborted"] = "running"
    content: str = ""
    timestamp: str = ""


TranscriptCollapsedActivityItem = Annotated[
    TranscriptToolUseBlock,
    Field(),
]


class TranscriptCollapsedActivityBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    type: Literal["collapsed_activity"] = "collapsed_activity"
    activityType: Literal["read"] = "read"
    count: int = Field(default=1, ge=1)
    blocks: list[TranscriptToolUseBlock] = Field(default_factory=list)


TranscriptBlock = Annotated[
    TranscriptUserBlock
    | TranscriptToolCallBlock
    | TranscriptToolResultBlock
    | TranscriptToolUseBlock
    | TranscriptAssistantTextBlock
    | TranscriptRunStatusBlock
    | TranscriptCollapsedActivityBlock,
    Field(discriminator="type"),
]


class ChatTranscriptHistoryResponse(BaseModel):
    sessionKey: str
    run: dict[str, Any] = Field(default_factory=dict)
    blocks: list[TranscriptBlock] = Field(default_factory=list)


class ChatTranscriptBlockEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["transcript.block"] = "transcript.block"
    sessionKey: str
    runId: str | None = None
    seq: int = Field(ge=0)
    op: Literal["append", "replace"] = "append"
    block: TranscriptBlock


class ChatTranscriptDoneEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["transcript.done"] = "transcript.done"
    sessionKey: str
    runId: str | None = None
    seq: int = Field(ge=0)


ChatTranscriptEvent = Annotated[
    ChatTranscriptBlockEvent | ChatTranscriptDoneEvent,
    Field(discriminator="type"),
]


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


class ChatConsoleSnapshotResponse(BaseModel):
    run: dict[str, Any] = Field(default_factory=dict)
    toolCalls: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    mainTasks: list[dict[str, Any]] = Field(default_factory=list)
    approvals: list[dict[str, Any]] = Field(default_factory=list)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


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


class ProfileImportResponse(BaseModel):
    ok: bool
    archive: str
    stateDir: str
    configPath: str
    stateBackup: str | None = None
    configBackup: str | None = None
    format: str


class RestartResponse(BaseModel):
    ok: bool
    message: str


# ── 节点控制模块 ──────────────────────────────────────────────────────────


class NodeListResponse(BaseModel):
    ok: bool
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    onlineCount: int = 0
    totalCount: int = 0


class NodeDetailResponse(BaseModel):
    ok: bool
    node: dict[str, Any] | None = None
    capabilityScores: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None


class NodeActionResponse(BaseModel):
    ok: bool
    message: str = ""
    taskId: str | None = None


class TaskListResponse(BaseModel):
    ok: bool
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class TaskDetailResponse(BaseModel):
    ok: bool
    task: dict[str, Any] | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None


class TaskActionRequest(BaseModel):
    taskId: str = Field(min_length=1, max_length=100)
    reason: str = Field(default="", max_length=500)


class TaskSteerRequest(BaseModel):
    taskId: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)


class TaskSubmitRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=5000)
    priority: int = Field(default=5, ge=1, le=10)
    assignedNodeId: str = Field(default="", max_length=100)
    originChannel: str = Field(default="", max_length=100)
    originChatId: str = Field(default="", max_length=200)


class ApprovalListResponse(BaseModel):
    ok: bool
    approvals: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class ApprovalDecideRequest(BaseModel):
    approvalId: str = Field(min_length=1, max_length=100)
    decision: Literal["approved", "rejected", "revised"]
    decidedBy: str = Field(default="webui", max_length=100)


class DeltaListResponse(BaseModel):
    ok: bool
    deltas: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class NodeOverviewResponse(BaseModel):
    ok: bool
    onlineNodes: int = 0
    totalNodes: int = 0
    runningTasks: int = 0
    pendingApprovals: int = 0
    pendingDeltas: int = 0
    taskStatusCounts: dict[str, int] = Field(default_factory=dict)
