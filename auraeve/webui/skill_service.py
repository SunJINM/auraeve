from __future__ import annotations

from pathlib import Path
from typing import Any

from auraeve.skill_system.service import (
    build_skill_status_report,
    disable_skill,
    doctor_skills,
    enable_skill,
    get_skill_info,
    install_skill_from_clawhub,
    install_skill_dependency,
    list_skills,
    sync_skills,
    install_skill_from_upload,
)


class SkillWebService:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def list(self) -> dict[str, Any]:
        return {"ok": True, "skills": list_skills(self.workspace)}

    def info(self, skill_id: str) -> dict[str, Any]:
        item = get_skill_info(self.workspace, skill_id)
        if item is None:
            return {"ok": False, "message": f"skill not found: {skill_id}"}
        return {"ok": True, "skill": item}

    def status(self) -> dict[str, Any]:
        return build_skill_status_report(self.workspace)

    def install(self, skill_id: str, install_id: str | None = None) -> dict[str, Any]:
        return install_skill_dependency(self.workspace, skill_id, install_id=install_id)

    def install_from_hub(
        self,
        slug: str,
        version: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        return install_skill_from_clawhub(self.workspace, slug, version=version, force=force)

    def install_from_upload(self, upload_id: str, force: bool = False) -> dict[str, Any]:
        return install_skill_from_upload(self.workspace, upload_id, force=force)

    def enable(self, skill_key: str) -> dict[str, Any]:
        return enable_skill(skill_key)

    def disable(self, skill_key: str) -> dict[str, Any]:
        return disable_skill(skill_key)

    def doctor(self) -> dict[str, Any]:
        return doctor_skills(self.workspace)

    def sync(self, all_skills: bool = False, dry_run: bool = False) -> dict[str, Any]:
        return sync_skills(self.workspace, all_skills=all_skills, dry_run=dry_run)
