from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ExternalAgentTarget:
    id: str
    kind: str = "coding"
    supports_session: bool = True
    supports_cwd: bool = True
    supports_cancel: bool = True
    supports_options: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExternalSessionHandle:
    session_id: str
    target: str
    mode: str
    cwd: str
    status: str
    created_at: float
    updated_at: float
    origin_session_key: str
    execution_target: str
    backend_session_ref: str | None = None
    node_id: str | None = None
    last_run_summary: str | None = None
    last_error: str | None = None


@dataclass(slots=True)
class ExternalRunRequest:
    task: str
    target: str
    cwd: str
    mode: str
    label: str | None
    timeout_s: int
    context_mode: str
    expected_output: str
    session_id: str | None
    execution_target: str


@dataclass(slots=True)
class ExternalRunResult:
    status: str
    target: str
    session_id: str
    final_text: str
    summary: str
    artifacts: list[dict]
    raw_output_ref: str | None
    error: str | None
    usage: dict[str, int]
    suggested_next_action: str | None
    error_type: str | None = None
    retryable: bool = False
    session_survived: bool = False

