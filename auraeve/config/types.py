from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ConfigSnapshot:
    path: Path
    exists: bool
    raw: str | None
    parsed: dict[str, Any]
    resolved: dict[str, Any]
    config: dict[str, Any]
    valid: bool
    issues: list[dict[str, str]]
    warnings: list[dict[str, str]]
    base_hash: str


WriteConfigResult = tuple[bool, ConfigSnapshot, list[str], list[str], list[dict[str, str]]]
