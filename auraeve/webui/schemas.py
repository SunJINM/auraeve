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
    approvals: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)

