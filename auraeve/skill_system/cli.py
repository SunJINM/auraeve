from __future__ import annotations

import json
from pathlib import Path

from .service import (
    build_skill_status_report,
    disable_skill,
    doctor_skills,
    enable_skill,
    get_skill_info,
    install_skill_dependency,
    list_skills,
    sync_skills,
)


def list_command(workspace: Path, *, as_json: bool = False) -> int:
    items = list_skills(workspace)
    if as_json:
        print(json.dumps({"skills": items}, ensure_ascii=False, indent=2))
        return 0
    if not items:
        print("No skills found.")
        return 0
    for item in items:
        status = "eligible" if item.get("eligible") else "ineligible"
        print(f"- {item.get('name')} [{status}] source={item.get('source')}")
    return 0


def info_command(workspace: Path, skill: str, *, as_json: bool = False) -> int:
    item = get_skill_info(workspace, skill)
    if item is None:
        print(f"Skill not found: {skill}")
        return 1
    print(json.dumps(item, ensure_ascii=False, indent=2))
    return 0


def status_command(workspace: Path, *, as_json: bool = False) -> int:
    report = build_skill_status_report(workspace)
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"Skills: {len(report.get('skills') or [])}")
    return 0


def install_command(workspace: Path, skill: str, install_id: str | None = None, *, as_json: bool = False) -> int:
    result = install_skill_dependency(workspace, skill, install_id=install_id)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("message") or ("Installed" if result.get("ok") else "Install failed"))
    return 0 if result.get("ok") else 1


def enable_command(skill_key: str, *, as_json: bool = False) -> int:
    result = enable_skill(skill_key)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Enabled skill: {skill_key}")
    return 0 if result.get("ok") else 1


def disable_command(skill_key: str, *, as_json: bool = False) -> int:
    result = disable_skill(skill_key)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Disabled skill: {skill_key}")
    return 0 if result.get("ok") else 1


def doctor_command(workspace: Path, *, as_json: bool = False) -> int:
    result = doctor_skills(workspace)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    if result.get("ok"):
        print("Skills doctor: OK")
        return 0
    print("Skills doctor found issues:")
    for issue in result.get("issues") or []:
        print(f"- {issue.get('code')}: {issue.get('message')}")
    return 1


def sync_command(workspace: Path, *, all_skills: bool = False, dry_run: bool = False, as_json: bool = False) -> int:
    result = sync_skills(workspace, all_skills=all_skills, dry_run=dry_run)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("message") or ("sync done" if result.get("ok") else "sync failed"))
    return 0 if result.get("ok") else 1
