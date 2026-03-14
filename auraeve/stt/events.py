from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from auraeve.observability import get_observability

def write_audit_line(payload: dict[str, Any]) -> None:
    event = dict(payload)
    event.setdefault("ts", datetime.now(timezone.utc).isoformat())
    get_observability().emit_audit(
        subsystem="stt",
        action="stt.transcribe",
        attrs=event,
        )

