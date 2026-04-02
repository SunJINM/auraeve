from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .defaults import DEFAULTS
from .io import read_config_snapshot, write_config
from .paths import resolve_config_path


def _strip_json_comments(raw: str) -> str:
    out: list[str] = []
    i = 0
    in_string = False
    in_line_comment = False
    in_block_comment = False
    while i < len(raw):
        ch = raw[i]
        nxt = raw[i + 1] if i + 1 < len(raw) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_string:
            out.append(ch)
            if ch == "\\":
                if i + 1 < len(raw):
                    out.append(raw[i + 1])
                    i += 2
                    continue
            elif ch == "\"":
                in_string = False
            i += 1
            continue
        if ch == "\"":
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _load_raw_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return {}
    try:
        payload = json.loads(_strip_json_comments(path.read_text(encoding="utf-8")))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
    return out


def _as_str_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in value.items():
        if isinstance(k, str) and isinstance(v, str):
            out[k] = v
    return out


def _as_non_empty_str(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _migrate_legacy_mcp_keys(raw_obj: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    out = dict(raw_obj)
    notes: list[str] = []
    has_legacy_servers = "MCP_SERVERS" in out
    has_legacy_reload = "MCP_HOT_RELOAD_ENABLED" in out

    if not has_legacy_servers and not has_legacy_reload:
        return out, notes

    legacy_servers = out.get("MCP_SERVERS")
    legacy_reload = out.get("MCP_HOT_RELOAD_ENABLED")

    if "MCP" not in out:
        servers: dict[str, Any] = {}
        if isinstance(legacy_servers, dict):
            for server_id, cfg in legacy_servers.items():
                sid = _as_non_empty_str(server_id)
                if not sid or not isinstance(cfg, dict):
                    continue
                transport = _as_non_empty_str(cfg.get("transport")).lower()
                if transport not in {"stdio", "http"}:
                    transport = "http" if _as_non_empty_str(cfg.get("url")) else "stdio"
                command = _as_non_empty_str(cfg.get("command")) or _as_non_empty_str(cfg.get("cmd"))
                url = _as_non_empty_str(cfg.get("url")) or _as_non_empty_str(cfg.get("endpoint"))
                server: dict[str, Any] = {
                    "enabled": bool(cfg.get("enabled", True)),
                    "transport": transport,
                    "command": command,
                    "args": _as_str_list(cfg.get("args")),
                    "env": _as_str_map(cfg.get("env")),
                    "url": url,
                    "headers": _as_str_map(cfg.get("headers")),
                    "toolPrefix": _as_non_empty_str(cfg.get("toolPrefix")),
                    "toolAllow": _as_str_list(cfg.get("toolAllow")),
                    "toolDeny": _as_str_list(cfg.get("toolDeny")),
                    "retry": {
                        "maxAttempts": int(cfg.get("retry", {}).get("maxAttempts", 3))
                        if isinstance(cfg.get("retry"), dict)
                        and isinstance(cfg.get("retry", {}).get("maxAttempts"), int)
                        else 3,
                        "backoffMs": int(cfg.get("retry", {}).get("backoffMs", 500))
                        if isinstance(cfg.get("retry"), dict)
                        and isinstance(cfg.get("retry", {}).get("backoffMs"), int)
                        else 500,
                    },
                    "healthcheck": {
                        "enabled": bool(cfg.get("healthcheck", {}).get("enabled", True))
                        if isinstance(cfg.get("healthcheck"), dict)
                        else True,
                        "intervalSec": int(cfg.get("healthcheck", {}).get("intervalSec", 60))
                        if isinstance(cfg.get("healthcheck"), dict)
                        and isinstance(cfg.get("healthcheck", {}).get("intervalSec"), int)
                        else 60,
                    },
                }
                servers[sid] = server

        reload_policy = "none" if legacy_reload is False else "diff"
        out["MCP"] = {
            "enabled": bool(servers),
            "reloadPolicy": reload_policy,
            "defaultTimeoutMs": 20000,
            "servers": servers,
        }
        notes.append("migrated legacy MCP_SERVERS/MCP_HOT_RELOAD_ENABLED to MCP")

    if has_legacy_servers:
        out.pop("MCP_SERVERS", None)
    if has_legacy_reload:
        out.pop("MCP_HOT_RELOAD_ENABLED", None)
        if "MCP" in out and isinstance(out.get("MCP"), dict):
            mcp_obj = dict(out["MCP"])
            if "reloadPolicy" not in mcp_obj:
                mcp_obj["reloadPolicy"] = "none" if legacy_reload is False else "diff"
                out["MCP"] = mcp_obj
    notes.append("removed legacy MCP keys: MCP_SERVERS/MCP_HOT_RELOAD_ENABLED")
    return out, notes


def run_config_doctor(*, fix: bool = False) -> dict[str, Any]:
    try:
        snapshot = read_config_snapshot()
        if snapshot.valid:
            return {
                "ok": True,
                "fixed": False,
                "path": str(snapshot.path),
                "issues": [],
                "warnings": [*snapshot.warnings],
            }

        issues = [*snapshot.issues]
        warnings = [*snapshot.warnings]
        if not fix:
            return {
                "ok": False,
                "fixed": False,
                "path": str(snapshot.path),
                "issues": issues,
                "warnings": warnings,
            }

        path = resolve_config_path()
        raw_obj = _load_raw_object(path)
        if raw_obj is None:
            # cannot parse, preserve a corrupt copy then reset to defaults
            if path.exists():
                corrupt = path.with_suffix(path.suffix + f".corrupt-{int(datetime.now(timezone.utc).timestamp())}")
                path.replace(corrupt)
            ok, next_snapshot, changed, requires_restart, write_issues = write_config(dict(DEFAULTS))
            return {
                "ok": bool(ok),
                "fixed": bool(ok),
                "path": str(next_snapshot.path),
                "issues": write_issues,
                "warnings": next_snapshot.warnings,
                "changed": changed,
                "requiresRestart": requires_restart,
            }

        raw_obj, migration_notes = _migrate_legacy_mcp_keys(raw_obj)

        # prune unknown keys; keep META if present
        allowed = set(DEFAULTS.keys()) | {"META"}
        cleaned = {k: v for k, v in raw_obj.items() if k in allowed}
        # remove known bad types by falling back to default value
        for issue in issues:
            path_key = issue.get("path", "")
            if path_key in DEFAULTS:
                cleaned[path_key] = DEFAULTS[path_key]

        ok, next_snapshot, changed, requires_restart, write_issues = write_config(cleaned)
        return {
            "ok": bool(ok),
            "fixed": bool(ok),
            "path": str(next_snapshot.path),
            "issues": write_issues,
            "warnings": [*next_snapshot.warnings, *({"path": "MCP", "message": n} for n in migration_notes)],
            "changed": changed,
            "requiresRestart": requires_restart,
        }
    finally:
        from auraeve.observability.manager import close_observability

        close_observability()
