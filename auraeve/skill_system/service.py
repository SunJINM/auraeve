from __future__ import annotations

import shutil
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from auraeve.config.paths import resolve_default_workspace_dir
from .discovery import discover_skill_entries
from .install_sources import install_skills_from_uploaded_archive
from .installers import install_spec
from .manifest import entry_to_dict, strip_frontmatter
from .models import SkillEntry
from .state import (
    load_skills_state,
    resolve_entry_settings,
    resolve_install_preferences,
    resolve_managed_skills_dir,
    save_skills_state,
)
from .status import (
    choose_install_spec,
    evaluate_skill_eligibility,
    explain_unrunnable_spec,
    normalize_install_options,
)


class EffectiveSkillsSettings:
    def __init__(
        self,
        enabled: bool,
        entries: dict[str, dict[str, Any]],
        extra_dirs: list[str],
        install: dict[str, Any],
        installs: dict[str, Any],
    ) -> None:
        self.enabled = enabled
        self.entries = entries
        self.extra_dirs = extra_dirs
        self.install = install
        self.installs = installs


def _decode_output(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    for enc in ("utf-8", "gbk", "cp936"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def _resolve_tool_path(names: list[str]) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    for candidate in [
        r"D:\nodejs\npx.cmd",
        r"D:\nodejs\npm.cmd",
        r"C:\Program Files\nodejs\npx.cmd",
        r"C:\Program Files\nodejs\npm.cmd",
        r"C:\Program Files (x86)\nodejs\npx.cmd",
        r"C:\Program Files (x86)\nodejs\npm.cmd",
    ]:
        if Path(candidate).exists():
            return candidate
    return None


def _run_clawhub_with_fallback(argv_tail: list[str]) -> dict[str, Any]:
    clawhub_bin = _resolve_tool_path(["clawhub", "clawhub.cmd"])
    npx_bin = _resolve_tool_path(["npx", "npx.cmd"])
    npm_bin = _resolve_tool_path(["npm", "npm.cmd"])

    commands: list[list[str]] = []
    if clawhub_bin:
        commands.append([clawhub_bin, *argv_tail])
    else:
        commands.append(["clawhub", *argv_tail])
    if npx_bin:
        commands.append([npx_bin, "-y", "clawhub", *argv_tail])
    else:
        commands.append(["npx", "-y", "clawhub", *argv_tail])
    if npm_bin:
        commands.append([npm_bin, "exec", "--yes", "clawhub", "--", *argv_tail])
    else:
        commands.append(["npm", "exec", "--yes", "clawhub", "--", *argv_tail])

    last_error: str | None = None
    attempted: list[str] = []
    for argv in commands:
        attempted.append(" ".join(argv))
        try:
            completed = subprocess.run(argv, capture_output=True, text=False, check=False)
            return {
                "ok": completed.returncode == 0,
                "code": completed.returncode,
                "stdout": _decode_output(completed.stdout).strip(),
                "stderr": _decode_output(completed.stderr).strip(),
                "runner": " ".join(argv[:3]) if len(argv) >= 3 else " ".join(argv),
                "attempted": attempted,
            }
        except FileNotFoundError as exc:
            last_error = str(exc)
            continue
    return {
        "ok": False,
        "code": None,
        "stdout": "",
        "stderr": (
            "Cannot execute clawhub via direct binary, npx, or npm exec. "
            "Install Node.js and ensure npm/npx are available to the AuraEve process PATH."
        ),
        "detail": last_error,
        "attempted": attempted,
    }


def _run_skillhub_with_fallback(argv_tail: list[str]) -> dict[str, Any]:
    skillhub_bin = _resolve_tool_path(["skillhub", "skillhub.cmd"])
    commands: list[list[str]] = []
    if skillhub_bin:
        commands.append([skillhub_bin, *argv_tail])
    else:
        commands.append(["skillhub", *argv_tail])

    last_error: str | None = None
    attempted: list[str] = []
    for argv in commands:
        attempted.append(" ".join(argv))
        try:
            completed = subprocess.run(argv, capture_output=True, text=False, check=False)
            return {
                "ok": completed.returncode == 0,
                "code": completed.returncode,
                "stdout": _decode_output(completed.stdout).strip(),
                "stderr": _decode_output(completed.stderr).strip(),
                "runner": " ".join(argv[:3]) if len(argv) >= 3 else " ".join(argv),
                "attempted": attempted,
            }
        except FileNotFoundError as exc:
            last_error = str(exc)
            continue

    return {
        "ok": False,
        "code": None,
        "stdout": "",
        "stderr": (
            "Cannot execute skillhub CLI. Install it first, then ensure 'skillhub' is in PATH."
        ),
        "detail": last_error,
        "attempted": attempted,
    }


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        val = (item or "").strip()
        if not val or val in seen:
            continue
        seen.add(val)
        out.append(val)
    return out


def _resolve_hub_candidates(raw: str) -> tuple[str, list[str]]:
    normalized = (raw or "").strip()
    if not normalized:
        return "hub", []

    lower = normalized.lower()
    if lower.startswith("skillhub install "):
        parts = normalized.split()
        if len(parts) >= 3:
            return "skillhub.tencent", [parts[2].strip()]
        return "skillhub.tencent", []
    if lower.startswith("skillhub:"):
        return "skillhub.tencent", [normalized.split(":", 1)[1].strip()]
    if lower.startswith("skillhub://"):
        return "skillhub.tencent", [normalized.split("://", 1)[1].strip()]
    if lower.startswith("clawhub:"):
        return "clawhub", [normalized.split(":", 1)[1].strip()]
    if lower.startswith("clawhub://"):
        return "clawhub", [normalized.split("://", 1)[1].strip()]

    if not (normalized.startswith("http://") or normalized.startswith("https://")):
        return "auto", [normalized]

    try:
        from urllib.parse import urlparse

        parsed = urlparse(normalized)
        host = (parsed.netloc or "").lower()
        parts = [p for p in parsed.path.split("/") if p]
    except Exception:
        return "hub", [normalized]

    provider = "hub"
    if host.endswith("clawhub.ai"):
        provider = "clawhub"
    elif host.endswith("skillhub.tencent.com"):
        provider = "skillhub.tencent"

    if provider == "hub":
        return provider, [normalized]

    candidates: list[str] = [normalized]
    if len(parts) >= 2:
        candidates.append(f"{parts[-2]}/{parts[-1]}")
        candidates.append(parts[-1])
    elif len(parts) == 1:
        candidates.append(parts[0])
    return provider, _dedupe_preserve_order(candidates)

def _read_runtime_config() -> dict[str, Any]:
    import auraeve.config as cfg
    workspace_resolver = getattr(cfg, "resolve_workspace_dir", None)
    workspace_path = (
        workspace_resolver("default")
        if callable(workspace_resolver)
        else resolve_default_workspace_dir()
    )

    return {
        "SKILLS_ENABLED": getattr(cfg, "SKILLS_ENABLED", True),
        "SKILLS_ENTRIES": getattr(cfg, "SKILLS_ENTRIES", {}),
        "SKILLS_LOAD_EXTRA_DIRS": getattr(cfg, "SKILLS_LOAD_EXTRA_DIRS", []),
        "SKILLS_INSTALL_NODE_MANAGER": getattr(cfg, "SKILLS_INSTALL_NODE_MANAGER", "npm"),
        "SKILLS_INSTALL_PREFER_BREW": getattr(cfg, "SKILLS_INSTALL_PREFER_BREW", True),
        "SKILLS_INSTALL_TIMEOUT_MS": getattr(cfg, "SKILLS_INSTALL_TIMEOUT_MS", 300000),
        "SKILLS_SECURITY_ALLOWED_DOWNLOAD_DOMAINS": getattr(
            cfg,
            "SKILLS_SECURITY_ALLOWED_DOWNLOAD_DOMAINS",
            [],
        ),
        "SKILLS_LIMIT_MAX_FILE_BYTES": getattr(cfg, "SKILLS_LIMIT_MAX_FILE_BYTES", 256000),
        "WORKSPACE_PATH": str(workspace_path),
    }


def resolve_effective_settings() -> EffectiveSkillsSettings:
    runtime = _read_runtime_config()
    state = load_skills_state()

    cfg_entries = runtime.get("SKILLS_ENTRIES") if isinstance(runtime.get("SKILLS_ENTRIES"), dict) else {}
    st_entries = state.get("entries") if isinstance(state.get("entries"), dict) else {}
    merged_entries = dict(cfg_entries)
    for key, value in st_entries.items():
        if not isinstance(value, dict):
            continue
        merged_entries[key] = {**(merged_entries.get(key, {}) if isinstance(merged_entries.get(key), dict) else {}), **value}

    cfg_extra = runtime.get("SKILLS_LOAD_EXTRA_DIRS") if isinstance(runtime.get("SKILLS_LOAD_EXTRA_DIRS"), list) else []
    st_extra = ((state.get("load") or {}).get("extraDirs") if isinstance(state.get("load"), dict) else [])
    merged_extra = []
    for item in [*cfg_extra, *st_extra]:
        if isinstance(item, str):
            val = item.strip()
            if val and val not in merged_extra:
                merged_extra.append(val)

    install = state.get("install") if isinstance(state.get("install"), dict) else {}
    install = {
        **install,
        "nodeManager": str(runtime.get("SKILLS_INSTALL_NODE_MANAGER", install.get("nodeManager", "npm"))),
        "preferBrew": bool(runtime.get("SKILLS_INSTALL_PREFER_BREW", install.get("preferBrew", True))),
        "timeoutMs": int(runtime.get("SKILLS_INSTALL_TIMEOUT_MS", install.get("timeoutMs", 300000))),
        "allowDownloadDomains": runtime.get(
            "SKILLS_SECURITY_ALLOWED_DOWNLOAD_DOMAINS",
            install.get("allowDownloadDomains", []),
        ),
    }

    installs = state.get("installs") if isinstance(state.get("installs"), dict) else {}

    return EffectiveSkillsSettings(
        enabled=bool(runtime.get("SKILLS_ENABLED", True)),
        entries=merged_entries,
        extra_dirs=merged_extra,
        install=install,
        installs=installs,
    )


def _resolve_workspace(workspace: Path | None) -> Path:
    if workspace:
        return workspace.resolve()
    runtime = _read_runtime_config()
    return Path(runtime.get("WORKSPACE_PATH") or resolve_default_workspace_dir()).resolve()


def _resolve_skill_key(entry: SkillEntry) -> str:
    return entry.metadata.skill_key or entry.name


def list_skills(workspace: Path | None = None) -> list[dict[str, Any]]:
    workspace_dir = _resolve_workspace(workspace)
    settings = resolve_effective_settings()
    entries = discover_skill_entries(
        workspace_dir,
        extra_dirs=settings.extra_dirs,
        max_skill_file_bytes=int(_read_runtime_config().get("SKILLS_LIMIT_MAX_FILE_BYTES", 256000)),
    )
    out: list[dict[str, Any]] = []
    for entry in entries:
        key = _resolve_skill_key(entry)
        entry_settings = resolve_entry_settings({"entries": settings.entries}, key)
        eligibility = evaluate_skill_eligibility(entry, entry_settings)
        prefs = resolve_install_preferences({"install": settings.install})
        out.append(
            {
                **entry_to_dict(entry),
                "skillKey": key,
                "enabled": entry_settings.enabled if entry_settings.enabled is not None else True,
                "eligible": bool(settings.enabled and eligibility.eligible),
                "missing": {
                    "bins": eligibility.missing_bins,
                    "anyBins": eligibility.missing_any_bins,
                    "env": eligibility.missing_env,
                    "config": eligibility.missing_config,
                    "os": eligibility.missing_os,
                },
                "install": normalize_install_options(entry, prefs),
                "stateInstall": settings.installs.get(key),
            }
        )
    out.sort(key=lambda x: x["name"])
    return out


def get_skill_info(workspace: Path | None, skill_name: str) -> dict[str, Any] | None:
    for item in list_skills(workspace):
        if item["name"] == skill_name or item["skillKey"] == skill_name:
            return item
    return None


def build_skill_status_report(workspace: Path | None = None) -> dict[str, Any]:
    skills = list_skills(workspace)
    return {
        "ok": True,
        "skills": skills,
        "workspace": str(_resolve_workspace(workspace)),
        "managedSkillsDir": str(resolve_managed_skills_dir()),
    }


def _find_entry(workspace: Path, name_or_key: str) -> SkillEntry | None:
    settings = resolve_effective_settings()
    entries = discover_skill_entries(workspace, extra_dirs=settings.extra_dirs)
    for entry in entries:
        if entry.name == name_or_key or _resolve_skill_key(entry) == name_or_key:
            return entry
    return None


def install_skill_dependency(
    workspace: Path | None,
    skill_name: str,
    install_id: str | None = None,
) -> dict[str, Any]:
    workspace_dir = _resolve_workspace(workspace)
    settings = resolve_effective_settings()
    entry = _find_entry(workspace_dir, skill_name)
    if entry is None:
        return {"ok": False, "message": f"skill not found: {skill_name}"}

    prefs_state = {"install": settings.install}
    prefs = resolve_install_preferences(prefs_state)
    spec = choose_install_spec(entry, prefs, install_id=install_id)
    if spec is None:
        if install_id:
            for candidate in entry.metadata.install_specs:
                sid = (candidate.id or "").strip()
                if sid and sid == install_id:
                    reason = explain_unrunnable_spec(candidate, prefs)
                    if reason:
                        return {
                            "ok": False,
                            "message": f"installer '{install_id}' is not runnable: {reason}",
                            "skill": entry.name,
                            "skillKey": _resolve_skill_key(entry),
                            "installId": install_id,
                        }
                    return {"ok": False, "message": f"installer not found: {install_id}"}
            return {"ok": False, "message": f"installer not found: {install_id}"}

        unavailable: list[str] = []
        for candidate in entry.metadata.install_specs:
            reason = explain_unrunnable_spec(candidate, prefs)
            if reason:
                sid = candidate.id or candidate.kind
                unavailable.append(f"{sid} ({reason})")
        if unavailable:
            return {
                "ok": False,
                "message": "no runnable installer found for current environment",
                "detail": "; ".join(unavailable),
                "skill": entry.name,
                "skillKey": _resolve_skill_key(entry),
            }
        return {"ok": False, "message": "installer not found"}

    result = install_spec(entry, spec, prefs)
    payload = asdict(result)
    payload["skill"] = entry.name
    payload["skillKey"] = _resolve_skill_key(entry)
    payload["installId"] = spec.id or install_id

    if result.ok:
        state = load_skills_state()
        installs = state.setdefault("installs", {})
        if not isinstance(installs, dict):
            installs = {}
            state["installs"] = installs
        installs[_resolve_skill_key(entry)] = {
            "skill": entry.name,
            "skillKey": _resolve_skill_key(entry),
            "installId": spec.id or install_id,
            "kind": spec.kind,
            "installedAt": datetime.now(timezone.utc).isoformat(),
            "spec": asdict(spec),
        }
        save_skills_state(state)

    return payload


def _set_skill_enabled(skill_key: str, enabled: bool) -> dict[str, Any]:
    state = load_skills_state()
    entries = state.setdefault("entries", {})
    if not isinstance(entries, dict):
        entries = {}
        state["entries"] = entries
    entry = entries.get(skill_key)
    if not isinstance(entry, dict):
        entry = {}
    entry["enabled"] = bool(enabled)
    entries[skill_key] = entry
    save_skills_state(state)
    return {"ok": True, "skillKey": skill_key, "enabled": bool(enabled)}


def enable_skill(skill_key: str) -> dict[str, Any]:
    return _set_skill_enabled(skill_key, True)


def disable_skill(skill_key: str) -> dict[str, Any]:
    return _set_skill_enabled(skill_key, False)


def doctor_skills(workspace: Path | None = None) -> dict[str, Any]:
    workspace_dir = _resolve_workspace(workspace)
    issues: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for item in list_skills(workspace_dir):
        name = item["name"]
        if name in seen_names:
            issues.append({"code": "duplicate_name", "message": f"duplicate skill name: {name}"})
        seen_names.add(name)

        skill_file = Path(item["skillFile"])
        if not skill_file.exists():
            issues.append(
                {
                    "code": "missing_skill_file",
                    "skill": name,
                    "message": f"SKILL.md missing: {skill_file}",
                }
            )

        if item["install"] and item["missing"]["bins"]:
            issues.append(
                {
                    "code": "missing_bins",
                    "skill": name,
                    "message": f"missing bins: {', '.join(item['missing']['bins'])}",
                }
            )

    return {"ok": len(issues) == 0, "issues": issues, "skills": list_skills(workspace_dir)}


def sync_skills(
    workspace: Path | None,
    *,
    all_skills: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    workspace_dir = _resolve_workspace(workspace)
    base_args = ["sync"]
    if all_skills:
        base_args.append("--all")
    if dry_run:
        base_args.append("--dry-run")
    base_args.extend(["--workdir", str(workspace_dir)])

    result = _run_clawhub_with_fallback(base_args)
    return {
        **result,
        "message": "sync completed" if result.get("ok") else "sync failed",
    }


def install_skill_from_clawhub(
    workspace: Path | None,
    slug: str,
    *,
    version: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    workspace_dir = _resolve_workspace(workspace)
    normalized_slug = slug.strip()
    if not normalized_slug:
        return {"ok": False, "message": "skill slug is required", "code": None}

    provider, candidates = _resolve_hub_candidates(normalized_slug)
    if not candidates:
        return {"ok": False, "message": "skill slug is required", "code": None}

    version_val = version.strip() if isinstance(version, str) and version.strip() else None
    attempts: list[dict[str, Any]] = []
    providers_to_try = [provider] if provider in {"clawhub", "skillhub.tencent"} else ["clawhub", "skillhub.tencent"]
    for provider_name in providers_to_try:
        provider_label = "SkillHub Tencent" if provider_name == "skillhub.tencent" else "ClawHub"
        for candidate in candidates:
            if provider_name == "skillhub.tencent":
                argv = ["install", candidate]
                # Keep soft compatibility if CLI supports these flags.
                if version_val:
                    argv.extend(["--version", version_val])
                if force:
                    argv.append("--force")
                result = _run_skillhub_with_fallback(argv)
            else:
                argv = ["install", candidate, "--workdir", str(workspace_dir)]
                if version_val:
                    argv.extend(["--version", version_val])
                if force:
                    argv.append("--force")
                result = _run_clawhub_with_fallback(argv)

            attempts.append({"provider": provider_name, "candidate": candidate, **result})
            if result.get("ok"):
                return {
                    **result,
                    "slug": candidate,
                    "provider": provider_name,
                    "version": version_val,
                    "message": f"Installed skill from {provider_label}: {candidate}",
                }

    last = attempts[-1] if attempts else {"ok": False, "stderr": "", "stdout": "", "code": None}
    detail = "; ".join(
        f"{a.get('provider')}:{a.get('candidate')}: {(a.get('stderr') or a.get('stdout') or 'failed').strip()}"
        for a in attempts
    )
    return {
        **last,
        "slug": normalized_slug,
        "provider": provider if provider != "auto" else "auto",
        "version": version_val,
        "message": "Hub install failed",
        "detail": detail,
    }


def install_skill_from_upload(
    workspace: Path | None,
    upload_id: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    _ = _resolve_workspace(workspace)
    normalized = (upload_id or "").strip()
    if not normalized:
        return {"ok": False, "message": "uploadId is required"}
    return install_skills_from_uploaded_archive(normalized, force=force)


def build_skills_prompt(
    workspace: Path,
    *,
    max_skills_in_prompt: int = 150,
    max_skills_prompt_chars: int = 30_000,
) -> str:
    settings = resolve_effective_settings()
    if not settings.enabled:
        return ""

    discovered = discover_skill_entries(workspace, extra_dirs=settings.extra_dirs)
    eligible_entries: list[SkillEntry] = []
    for entry in discovered:
        key = _resolve_skill_key(entry)
        entry_settings = resolve_entry_settings({"entries": settings.entries}, key)
        eligibility = evaluate_skill_eligibility(entry, entry_settings)
        if eligibility.eligible:
            eligible_entries.append(entry)

    prompt_entries = [e for e in eligible_entries if not e.metadata.disable_model_invocation]
    if not prompt_entries:
        return ""

    always = [e for e in prompt_entries if e.metadata.always]
    normal = [e for e in prompt_entries if not e.metadata.always]

    parts: list[str] = []
    if always:
        always_blocks: list[str] = []
        for entry in always:
            try:
                content = entry.skill_file.read_text(encoding="utf-8")
            except Exception:
                continue
            body = strip_frontmatter(content)
            if body:
                always_blocks.append(f"### {entry.name}\n\n{body}")
        if always_blocks:
            parts.append("# Always Skills\n\n" + "\n\n---\n\n".join(always_blocks))

    lines: list[str] = []
    for entry in normal[: max(0, max_skills_in_prompt)]:
        lines.append(
            "  <skill>\n"
            f"    <name>{entry.name}</name>\n"
            f"    <description>{entry.description}</description>\n"
            f"    <location>{entry.skill_file}</location>\n"
            "  </skill>"
        )

    if lines:
        skills_xml = "<skills>\n" + "\n".join(lines) + "\n</skills>"
        parts.append(
            "# Available Skills\n"
            "Before replying, scan skill descriptions and read at most one matching SKILL.md via read_file.\n\n"
            + skills_xml
        )

    block = "\n\n---\n\n".join(parts)
    if len(block) <= max_skills_prompt_chars:
        return block

    # trim list section first
    while len(block) > max_skills_prompt_chars and lines:
        lines.pop()
        skills_xml = "<skills>\n" + "\n".join(lines) + "\n</skills>" if lines else ""
        parts_trimmed = parts[:1] if parts and parts[0].startswith("# Always Skills") else []
        if skills_xml:
            parts_trimmed.append(
                "# Available Skills\n"
                "Before replying, scan skill descriptions and read at most one matching SKILL.md via read_file.\n\n"
                + skills_xml
            )
        block = "\n\n---\n\n".join(parts_trimmed)

    return block[:max_skills_prompt_chars]

