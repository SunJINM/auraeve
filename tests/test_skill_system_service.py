from __future__ import annotations

from pathlib import Path

from auraeve.skill_system.models import SkillEligibility, SkillEntry, SkillMetadata
from auraeve.skill_system.service import EffectiveSkillsSettings, build_skills_prompt


def test_build_skills_prompt_uses_read_tool_name(tmp_path: Path, monkeypatch) -> None:
    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("---\nname: demo\ndescription: demo skill\n---\nbody", encoding="utf-8")

    entry = SkillEntry(
        name="demo",
        description="demo skill",
        skill_file=skill_file,
        base_dir=skill_dir,
        source="workspace",
        metadata=SkillMetadata(),
    )

    monkeypatch.setattr(
        "auraeve.skill_system.service.resolve_effective_settings",
        lambda: EffectiveSkillsSettings(
            enabled=True,
            entries={},
            extra_dirs=[],
            install={},
            installs={},
        ),
    )
    monkeypatch.setattr(
        "auraeve.skill_system.service.discover_skill_entries",
        lambda workspace, extra_dirs=None: [entry],
    )
    monkeypatch.setattr(
        "auraeve.skill_system.service.evaluate_skill_eligibility",
        lambda entry, entry_settings: SkillEligibility(eligible=True),
    )

    prompt = build_skills_prompt(tmp_path)

    assert "via Read" in prompt
    assert "via read_file" not in prompt
