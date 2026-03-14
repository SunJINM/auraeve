from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import SkillEntry, SkillInstallSpec, SkillMetadata


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


def _parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _normalize_str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            val = item.strip()
            if val:
                out.append(val)
    return out


def parse_frontmatter(content: str) -> dict[str, str]:
    if not content.startswith("---"):
        return {}
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}
    block = match.group(1)
    result: dict[str, str] = {}
    last_key: str | None = None
    for line in block.splitlines():
        if not line.strip():
            continue
        if line.startswith(" ") or line.startswith("\t"):
            if last_key:
                result[last_key] = result.get(last_key, "") + "\n" + line.strip()
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        result[key] = value
        last_key = key
    return result


def strip_frontmatter(content: str) -> str:
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return content.strip()
    return content[match.end() :].strip()


def _parse_metadata(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    text = raw.strip()
    # tolerate yaml-like multiline json
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    if isinstance(parsed.get("auraeve"), dict):
        return parsed["auraeve"]
    if isinstance(parsed.get("openclaw"), dict):
        return parsed["openclaw"]
    if isinstance(parsed.get("nanobot"), dict):
        return parsed["nanobot"]
    return parsed


def _parse_install_specs(raw: Any) -> list[SkillInstallSpec]:
    if not isinstance(raw, list):
        return []
    out: list[SkillInstallSpec] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).strip().lower()
        if kind not in {"brew", "node", "go", "uv", "download", "apt"}:
            continue
        spec = SkillInstallSpec(
            kind=kind,
            id=str(item.get("id", "")).strip() or None,
            label=str(item.get("label", "")).strip() or None,
            bins=_normalize_str_list(item.get("bins")),
            os=_normalize_str_list(item.get("os")),
            formula=str(item.get("formula", "")).strip() or None,
            package=str(item.get("package", "")).strip() or None,
            module=str(item.get("module", "")).strip() or None,
            url=str(item.get("url", "")).strip() or None,
            archive=str(item.get("archive", "")).strip() or None,
            extract=item.get("extract") if isinstance(item.get("extract"), bool) else None,
            strip_components=item.get("stripComponents")
            if isinstance(item.get("stripComponents"), int)
            else None,
            target_dir=str(item.get("targetDir", "")).strip() or None,
        )
        out.append(spec)
    return out


def build_skill_metadata(frontmatter: dict[str, str]) -> SkillMetadata:
    metadata = _parse_metadata(frontmatter.get("metadata", ""))
    requires = metadata.get("requires") if isinstance(metadata.get("requires"), dict) else {}
    return SkillMetadata(
        skill_key=(str(metadata.get("skillKey", "")).strip() or None),
        primary_env=(str(metadata.get("primaryEnv", "")).strip() or None),
        always=_parse_bool(metadata.get("always"), False),
        user_invocable=_parse_bool(
            frontmatter.get("user-invocable", metadata.get("userInvocable")),
            True,
        ),
        disable_model_invocation=_parse_bool(
            frontmatter.get("disable-model-invocation", metadata.get("disableModelInvocation")),
            False,
        ),
        emoji=(str(metadata.get("emoji", "")).strip() or None),
        homepage=(str(metadata.get("homepage", "")).strip() or None),
        os=_normalize_str_list(metadata.get("os")),
        requires_bins=_normalize_str_list(requires.get("bins")),
        requires_any_bins=_normalize_str_list(requires.get("anyBins")),
        requires_env=_normalize_str_list(requires.get("env")),
        requires_config=_normalize_str_list(requires.get("config")),
        install_specs=_parse_install_specs(metadata.get("install")),
    )


def parse_skill_entry(skill_dir: Path, source: str) -> SkillEntry | None:
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists() or not skill_file.is_file():
        return None
    try:
        content = skill_file.read_text(encoding="utf-8")
    except Exception:
        return None
    frontmatter = parse_frontmatter(content)
    metadata = build_skill_metadata(frontmatter)
    name = str(frontmatter.get("name", "")).strip() or skill_dir.name
    description = str(frontmatter.get("description", "")).strip() or name
    return SkillEntry(
        name=name,
        description=description,
        skill_file=skill_file.resolve(),
        base_dir=skill_dir.resolve(),
        source=source,
        metadata=metadata,
        frontmatter=frontmatter,
    )


def entry_to_dict(entry: SkillEntry) -> dict[str, Any]:
    return {
        "name": entry.name,
        "description": entry.description,
        "source": entry.source,
        "skillFile": str(entry.skill_file),
        "baseDir": str(entry.base_dir),
        "metadata": asdict(entry.metadata),
    }
