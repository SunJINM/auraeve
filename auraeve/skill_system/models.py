from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillInstallSpec:
    kind: str
    id: str | None = None
    label: str | None = None
    bins: list[str] = field(default_factory=list)
    os: list[str] = field(default_factory=list)
    formula: str | None = None
    package: str | None = None
    module: str | None = None
    url: str | None = None
    archive: str | None = None
    extract: bool | None = None
    strip_components: int | None = None
    target_dir: str | None = None


@dataclass
class SkillMetadata:
    skill_key: str | None = None
    primary_env: str | None = None
    always: bool = False
    user_invocable: bool = True
    disable_model_invocation: bool = False
    emoji: str | None = None
    homepage: str | None = None
    os: list[str] = field(default_factory=list)
    requires_bins: list[str] = field(default_factory=list)
    requires_any_bins: list[str] = field(default_factory=list)
    requires_env: list[str] = field(default_factory=list)
    requires_config: list[str] = field(default_factory=list)
    install_specs: list[SkillInstallSpec] = field(default_factory=list)


@dataclass
class SkillEntry:
    name: str
    description: str
    skill_file: Path
    base_dir: Path
    source: str
    metadata: SkillMetadata
    frontmatter: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillEligibility:
    eligible: bool
    missing_bins: list[str] = field(default_factory=list)
    missing_any_bins: list[str] = field(default_factory=list)
    missing_env: list[str] = field(default_factory=list)
    missing_config: list[str] = field(default_factory=list)
    missing_os: list[str] = field(default_factory=list)


@dataclass
class SkillInstallResult:
    ok: bool
    message: str
    code: int | None = None
    stdout: str = ""
    stderr: str = ""
    install_id: str | None = None


@dataclass
class SkillStateEntry:
    enabled: bool | None = None
    env: dict[str, str] = field(default_factory=dict)
    api_key: str | None = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillsInstallPreferences:
    node_manager: str = "npm"
    prefer_brew: bool = True
    timeout_ms: int = 300_000
    allow_download_domains: list[str] = field(default_factory=list)
