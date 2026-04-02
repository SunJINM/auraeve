from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

CommandMode = Literal["prompt", "task-notification", "cron", "heartbeat"]
CommandPriority = Literal["now", "next", "later"]


@dataclass(slots=True)
class QueuedCommand:
    session_key: str
    source: str
    mode: CommandMode
    priority: CommandPriority
    payload: dict[str, Any]
    origin: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    agent_id: str | None = None
