"""ExecutionRecord domain model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ExecutionRecord:
    execution_id: str
    session_id: str
    run_id: str
    command: str
    cwd: str
    exit_code: int
    stdout_summary: str = ""
    stderr_summary: str = ""
