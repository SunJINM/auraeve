from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class STTError(Exception):
    """Base STT error."""


class AuthError(STTError):
    """Authentication/authorization failed."""


class RateLimitError(STTError):
    """Provider rate limited."""


class TransientError(STTError):
    """Retryable transient failure."""


class PermanentError(STTError):
    """Non-retryable provider failure."""


@dataclass
class STTRequest:
    input_path: Path
    channel: str = ""
    language: str = ""
    provider_profile: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class STTAttempt:
    provider_id: str
    ok: bool
    latency_ms: int
    error: str = ""
    error_category: str = ""


@dataclass
class STTResult:
    ok: bool
    text: str | None = None
    language: str | None = None
    confidence: float | None = None
    provider: str = ""
    latency_ms: int = 0
    attempts: list[STTAttempt] = field(default_factory=list)
    segments: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    @property
    def provider_tried(self) -> list[str]:
        return [item.provider_id for item in self.attempts]


@dataclass
class ProviderProfile:
    id: str
    enabled: bool = True
    priority: int = 100
    model: str = ""
    api_base: str = ""
    api_key: str = ""
    formats: list[str] = field(default_factory=list)
    timeout_ms: int = 15000
    command: str = ""
    args_template: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeConfig:
    enabled: bool
    default_language: str
    timeout_ms: int
    max_concurrency: int
    retry_count: int
    failover_enabled: bool
    cache_enabled: bool
    cache_ttl_s: int
    providers: list[ProviderProfile]

