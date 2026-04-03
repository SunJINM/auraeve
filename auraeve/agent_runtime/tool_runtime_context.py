from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass(slots=True)
class FileReadSnapshot:
    file_path: str
    timestamp_ms: int
    file_mtime_ms: int
    is_partial_view: bool
    content_type: str = "text"
    content: str | None = None
    offset: int | None = None
    limit: int | None = None
    pages: str | None = None


@dataclass(slots=True)
class FileReadStateStore:
    snapshots: dict[str, FileReadSnapshot] = field(default_factory=dict)

    def record(self, snapshot: FileReadSnapshot) -> None:
        self.snapshots[snapshot.file_path] = snapshot

    def get(self, file_path: str) -> FileReadSnapshot | None:
        return self.snapshots.get(file_path)


@dataclass(slots=True)
class ToolRuntimeContext:
    file_reads: FileReadStateStore


_CURRENT_CONTEXT: ContextVar[ToolRuntimeContext | None] = ContextVar(
    "tool_runtime_context", default=None
)


@contextmanager
def use_tool_runtime_context(ctx: ToolRuntimeContext):
    token = _CURRENT_CONTEXT.set(ctx)
    try:
        yield
    finally:
        _CURRENT_CONTEXT.reset(token)


def get_current_tool_runtime_context() -> ToolRuntimeContext | None:
    return _CURRENT_CONTEXT.get()
