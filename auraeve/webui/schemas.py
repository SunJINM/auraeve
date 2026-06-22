from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatHistoryResponse(BaseModel):
    sessionKey: str
    messages: list[dict[str, Any]]


class TranscriptAttachmentItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = ""
    ref: str = ""
    kind: str = "file"
    mime: str = ""
    filename: str = ""
    url: str = ""
    downloadUrl: str = ""
    size: int = 0


class TranscriptUserBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    type: Literal["user"] = "user"
    content: str = ""
    timestamp: str = ""
    attachments: list[TranscriptAttachmentItem] = Field(default_factory=list)


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
    status: Literal["preparing", "running", "success", "error"] = "running"
    resources: list[dict[str, Any]] = Field(default_factory=list)


class TranscriptAssistantTextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    type: Literal["assistant_text"] = "assistant_text"
    content: str = ""
    timestamp: str = ""
    streaming: bool = False


class TranscriptImageItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = ""
    url: str = ""
    ref: str = ""
    mime: str = "image/png"
    alt: str = ""
    prompt: str = ""
    size: str = ""


class TranscriptImageBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    type: Literal["image"] = "image"
    status: Literal["generating", "ready", "error"] = "ready"
    images: list[TranscriptImageItem] = Field(default_factory=list)
    prompt: str = ""
    toolCallId: str = ""
    size: str = ""


TranscriptBlock = Annotated[
    TranscriptUserBlock
    | TranscriptToolCallBlock
    | TranscriptToolResultBlock
    | TranscriptToolUseBlock
    | TranscriptAssistantTextBlock
    | TranscriptImageBlock,
    Field(discriminator="type"),
]


class ChatTranscriptHistoryResponse(BaseModel):
    sessionKey: str
    run: dict[str, Any] = Field(default_factory=dict)
    blocks: list[TranscriptBlock] = Field(default_factory=list)


class ChatSessionMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1)
    title: str = "新对话"
    createdAt: int = Field(ge=0)
    updatedAt: int = Field(ge=0)


class ChatSessionsResponse(BaseModel):
    sessions: list[ChatSessionMeta] = Field(default_factory=list)


class ChatSessionCreateResponse(BaseModel):
    session: ChatSessionMeta


class ChatSessionDeleteResponse(BaseModel):
    ok: bool


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


class ChatAttachmentInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(min_length=1, max_length=200)
    filename: str = Field(default="file", max_length=255)
    mime: str = Field(default="", max_length=200)
    kind: str = Field(default="file", max_length=40)
    size: int = Field(default=0, ge=0)


class ChatSendRequest(BaseModel):
    sessionKey: str = Field(min_length=1, max_length=200)
    message: str = Field(default="", max_length=20000)
    idempotencyKey: str = Field(min_length=1, max_length=200)
    userId: str = Field(min_length=1, max_length=200)
    displayName: str | None = Field(default=None, max_length=200)
    attachments: list[ChatAttachmentInput] = Field(default_factory=list, max_length=20)


class ChatSendResponse(BaseModel):
    runId: str
    status: Literal["started", "in_flight"]


# data URL/base64 字段长度上限：与 media.MAX_FILE_BYTES(5MB) 对齐，原始数据经
# base64 膨胀约 4/3，再留 data URL 前缀余量。在反序列化层提前挡掉超大请求体，
# 避免已认证用户发巨型 JSON 撑爆内存（真实字节上限仍由 upload 端点二次校验）。
_MAX_UPLOAD_BASE64_LEN = 5 * 1024 * 1024 * 4 // 3 + 256


class ChatUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(default="file", max_length=255)
    mime: str = Field(default="", max_length=200)
    # 纯 base64 或 data URL（data:<mime>;base64,<data>）
    dataBase64: str = Field(min_length=1, max_length=_MAX_UPLOAD_BASE64_LEN)


class ChatUploadResponse(BaseModel):
    id: str
    ref: str
    kind: str
    mime: str
    filename: str
    url: str
    downloadUrl: str
    size: int


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
    approvals: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)

