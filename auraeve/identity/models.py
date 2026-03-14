from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class IdentityProfile:
    canonical_user_id: str
    display_name: str = ""
    relationship_to_assistant: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0


@dataclass
class IdentityBinding:
    channel: str
    external_user_id: str
    canonical_user_id: str
    confidence: float = 1.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class IdentityRelationship:
    canonical_user_id: str
    relationship_to_assistant: str
    confidence: float = 1.0
    source: str = ""
    updated_at: datetime = field(default_factory=datetime.now)
