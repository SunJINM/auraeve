"""Facade for the standalone skill system.

This module keeps the previous `SkillsLoader` API surface used by the
runtime/context builder, while delegating data discovery and prompt generation
to `auraeve.skill_system.service`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from auraeve.skill_system.service import build_skills_prompt, list_skills


@dataclass
class SkillEntry:
    name: str
    path: str
    source: str
    description: str = ""
    always: bool = False
    user_invocable: bool = True
    disable_model_invocation: bool = False
    requires_bins: list[str] = field(default_factory=list)
    requires_env: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    eligible: bool = True


DEFAULT_MAX_SKILLS_IN_PROMPT = 150
DEFAULT_MAX_SKILLS_PROMPT_CHARS = 30_000
DEFAULT_MAX_SKILL_FILE_BYTES = 256_000


class SkillsLoader:
    def __init__(
        self,
        workspace: Path,
        builtin_skills_dir: Path | None = None,
        managed_skills_dir: Path | None = None,
        max_skills_in_prompt: int = DEFAULT_MAX_SKILLS_IN_PROMPT,
        max_skills_prompt_chars: int = DEFAULT_MAX_SKILLS_PROMPT_CHARS,
        max_skill_file_bytes: int = DEFAULT_MAX_SKILL_FILE_BYTES,
    ) -> None:
        self.workspace = workspace
        self.max_skills_in_prompt = max_skills_in_prompt
        self.max_skills_prompt_chars = max_skills_prompt_chars
        self.max_skill_file_bytes = max_skill_file_bytes
        self._entries_cache: list[SkillEntry] | None = None

    def invalidate_cache(self) -> None:
        self._entries_cache = None

    def load_all_entries(self, use_cache: bool = True) -> list[SkillEntry]:
        if use_cache and self._entries_cache is not None:
            return self._entries_cache

        entries: list[SkillEntry] = []
        for item in list_skills(self.workspace):
            metadata = item.get("metadata") or {}
            requires = metadata.get("requires") if isinstance(metadata.get("requires"), dict) else {}
            entries.append(
                SkillEntry(
                    name=str(item.get("name", "")),
                    path=str(item.get("skillFile", "")),
                    source=str(item.get("source", "")),
                    description=str(item.get("description", "")),
                    always=bool(metadata.get("always", False)),
                    user_invocable=bool(metadata.get("user_invocable", metadata.get("userInvocable", True))),
                    disable_model_invocation=bool(
                        metadata.get("disable_model_invocation", metadata.get("disableModelInvocation", False))
                    ),
                    requires_bins=list(requires.get("bins", []) if isinstance(requires, dict) else []),
                    requires_env=list(requires.get("env", []) if isinstance(requires, dict) else []),
                    metadata=metadata,
                    eligible=bool(item.get("eligible", True)),
                )
            )

        self._entries_cache = entries
        return entries

    def get_eligible_entries(self, filter_unavailable: bool = True) -> list[SkillEntry]:
        entries = self.load_all_entries()
        if filter_unavailable:
            return [e for e in entries if e.eligible]
        return entries

    def get_always_entries(self) -> list[SkillEntry]:
        return [e for e in self.get_eligible_entries() if e.always]

    def get_user_invocable_specs(self) -> list[dict]:
        return [
            {"name": e.name, "description": (e.description or e.name)[:100]}
            for e in self.get_eligible_entries()
            if e.user_invocable
        ]

    def load_skill_content(self, name: str) -> str | None:
        for entry in self.load_all_entries():
            if entry.name != name:
                continue
            try:
                return Path(entry.path).read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    def load_skill_body(self, name: str) -> str | None:
        content = self.load_skill_content(name)
        if not content:
            return None
        if content.startswith("---"):
            marker = "\n---\n"
            idx = content.find(marker, 4)
            if idx >= 0:
                return content[idx + len(marker) :].strip()
        return content.strip()

    def build_skills_prompt(self) -> str:
        return build_skills_prompt(
            self.workspace,
            max_skills_in_prompt=self.max_skills_in_prompt,
            max_skills_prompt_chars=self.max_skills_prompt_chars,
        )
