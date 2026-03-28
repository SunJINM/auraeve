"""ApprovalRequest domain model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ApprovalRequest:
    approval_id: str
    session_id: str
    run_id: str
    action_type: str
    risk_level: str  # low | medium | high
    status: str      # pending | approved | rejected
    resolved_by: str | None = None
