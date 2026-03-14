from __future__ import annotations

import os
import shutil
import sys
from typing import Any

from .models import SkillEligibility, SkillEntry, SkillInstallSpec, SkillStateEntry, SkillsInstallPreferences


def _is_config_truthy(config_obj: dict[str, Any], path_str: str) -> bool:
    if not path_str:
        return False
    cur: Any = config_obj
    for key in path_str.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return False
        cur = cur.get(key)
    return bool(cur)


def evaluate_skill_eligibility(
    entry: SkillEntry,
    skill_settings: SkillStateEntry,
    *,
    runtime_config: dict[str, Any] | None = None,
) -> SkillEligibility:
    if skill_settings.enabled is False:
        return SkillEligibility(eligible=False)

    missing_os: list[str] = []
    if entry.metadata.os:
        if sys.platform not in entry.metadata.os:
            missing_os = entry.metadata.os

    missing_bins = [b for b in entry.metadata.requires_bins if not shutil.which(b)]
    any_bins = entry.metadata.requires_any_bins
    missing_any_bins: list[str] = []
    if any_bins and not any(shutil.which(b) for b in any_bins):
        missing_any_bins = any_bins

    missing_env: list[str] = []
    for env_name in entry.metadata.requires_env:
        if os.environ.get(env_name):
            continue
        if skill_settings.env.get(env_name):
            continue
        if skill_settings.api_key and entry.metadata.primary_env == env_name:
            continue
        missing_env.append(env_name)

    missing_config: list[str] = []
    for cfg_path in entry.metadata.requires_config:
        if not _is_config_truthy(runtime_config or {}, cfg_path):
            missing_config.append(cfg_path)

    eligible = not (missing_os or missing_bins or missing_any_bins or missing_env or missing_config)
    if entry.metadata.always:
        eligible = True

    return SkillEligibility(
        eligible=eligible,
        missing_bins=missing_bins,
        missing_any_bins=missing_any_bins,
        missing_env=missing_env,
        missing_config=missing_config,
        missing_os=missing_os,
    )


def _supports_current_os(spec: SkillInstallSpec) -> bool:
    if not spec.os:
        return True
    return sys.platform in spec.os


def _installer_command(spec: SkillInstallSpec, prefs: SkillsInstallPreferences) -> str | None:
    if spec.kind == "brew":
        return "brew"
    if spec.kind == "apt":
        return "apt-get"
    if spec.kind == "node":
        manager = (prefs.node_manager or "npm").strip().lower()
        if manager in {"pnpm", "yarn", "bun"}:
            return manager
        return "npm"
    if spec.kind == "go":
        return "go"
    if spec.kind == "uv":
        return "uv"
    if spec.kind == "download":
        return None
    return None


def _is_spec_runnable(spec: SkillInstallSpec, prefs: SkillsInstallPreferences) -> bool:
    cmd = _installer_command(spec, prefs)
    if not cmd:
        return spec.kind == "download"
    return shutil.which(cmd) is not None


def explain_unrunnable_spec(spec: SkillInstallSpec, prefs: SkillsInstallPreferences) -> str | None:
    if _is_spec_runnable(spec, prefs):
        return None
    cmd = _installer_command(spec, prefs)
    if not cmd:
        return "installer is not runnable on this environment"
    return f"required installer command not found: {cmd}"


def choose_install_spec(
    entry: SkillEntry,
    prefs: SkillsInstallPreferences,
    install_id: str | None = None,
) -> SkillInstallSpec | None:
    specs = [s for s in entry.metadata.install_specs if _supports_current_os(s)]
    if not specs:
        return None

    if install_id:
        for spec in specs:
            sid = (spec.id or "").strip()
            if sid and sid == install_id:
                return spec if _is_spec_runnable(spec, prefs) else None
        return None

    runnable = [s for s in specs if _is_spec_runnable(s, prefs)]
    if not runnable:
        return None

    node = next((s for s in runnable if s.kind == "node"), None)
    brew = next((s for s in runnable if s.kind == "brew"), None)
    uv = next((s for s in runnable if s.kind == "uv"), None)
    apt = next((s for s in runnable if s.kind == "apt"), None)
    go = next((s for s in runnable if s.kind == "go"), None)
    download = next((s for s in runnable if s.kind == "download"), None)

    if node:
        return node
    if prefs.prefer_brew and brew and shutil.which("brew"):
        return brew
    return uv or apt or (brew if shutil.which("brew") else None) or go or download or runnable[0]


def normalize_install_options(
    entry: SkillEntry,
    prefs: SkillsInstallPreferences | None = None,
) -> list[dict[str, Any]]:
    prefs = prefs or SkillsInstallPreferences()
    options: list[dict[str, Any]] = []
    for i, spec in enumerate(entry.metadata.install_specs):
        sid = (spec.id or f"{spec.kind}-{i}").strip()
        label = (spec.label or "").strip()
        if not label:
            if spec.kind == "brew" and spec.formula:
                label = f"Install {spec.formula} (brew)"
            elif spec.kind == "node" and spec.package:
                label = f"Install {spec.package} (node)"
            elif spec.kind == "go" and spec.module:
                label = f"Install {spec.module} (go)"
            elif spec.kind == "uv" and spec.package:
                label = f"Install {spec.package} (uv)"
            elif spec.kind == "apt" and spec.package:
                label = f"Install {spec.package} (apt)"
            elif spec.kind == "download" and spec.url:
                label = f"Download {spec.url}"
            else:
                label = "Run installer"
        reason = explain_unrunnable_spec(spec, prefs)
        options.append(
            {
                "id": sid,
                "kind": spec.kind,
                "label": label,
                "bins": spec.bins,
                "runnable": reason is None,
                "reason": reason,
            }
        )
    return options
