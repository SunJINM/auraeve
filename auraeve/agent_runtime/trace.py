from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RunTraceEvent:
    ts_ms: int
    kind: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RunTrace:
    session_id: str
    is_subagent: bool
    started_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    events: list[RunTraceEvent] = field(default_factory=list)
    stop_reason: str | None = None

    def add(self, kind: str, **data: Any) -> None:
        self.events.append(RunTraceEvent(ts_ms=int(time.time() * 1000), kind=kind, data=data))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "isSubagent": self.is_subagent,
            "startedAtMs": self.started_at_ms,
            "stopReason": self.stop_reason,
            "events": [
                {
                    "tsMs": evt.ts_ms,
                    "kind": evt.kind,
                    "data": evt.data,
                }
                for evt in self.events
            ],
        }

