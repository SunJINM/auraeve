from __future__ import annotations

import os
from pathlib import Path
from typing import Any


STATE_DIRNAME = ".auraeve"
CONFIG_FILENAME = "auraeve.json"
DEFAULT_AGENT_ID = "default"


def _resolve_user_path(raw: str) -> Path:
    expanded = Path(raw).expanduser()
    return Path(os.path.abspath(str(expanded)))


def resolve_home_dir() -> Path:
    home_env = os.environ.get("HOME", "").strip() or os.environ.get("USERPROFILE", "").strip()
    if home_env:
        return _resolve_user_path(home_env)
    return Path(os.path.abspath(str(Path.home())))


def resolve_state_dir(env: dict[str, str] | None = None) -> Path:
    effective_env = env if env is not None else os.environ
    override = str(effective_env.get("AURAEVE_STATE_DIR", "")).strip()
    if override:
        return _resolve_user_path(override)
    return (resolve_home_dir() / STATE_DIRNAME).resolve()


def resolve_config_path(env: dict[str, str] | None = None) -> Path:
    effective_env = env if env is not None else os.environ
    override = str(effective_env.get("AURAEVE_CONFIG_PATH", "")).strip()
    if override:
        return _resolve_user_path(override)
    return resolve_state_dir(effective_env) / CONFIG_FILENAME


def resolve_default_workspace_dir(env: dict[str, str] | None = None) -> Path:
    effective_env = env if env is not None else os.environ
    return (resolve_state_dir(effective_env) / "workspace").resolve()


def _resolve_workspace_path(raw: str) -> Path:
    p = Path(raw).expanduser()
    if p.is_absolute():
        return _resolve_user_path(str(p))
    return (Path.cwd() / p).resolve()


def _normalize_agent_id(agent_id: str | None) -> str:
    if not agent_id:
        return DEFAULT_AGENT_ID
    value = str(agent_id).strip().lower()
    if not value:
        return DEFAULT_AGENT_ID
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value).strip("-_")
    return safe or DEFAULT_AGENT_ID


def resolve_agents_dir(env: dict[str, str] | None = None) -> Path:
    effective_env = env if env is not None else os.environ
    return resolve_state_dir(effective_env) / "agents"


def resolve_agent_dir(agent_id: str | None = None, env: dict[str, str] | None = None) -> Path:
    effective_env = env if env is not None else os.environ
    return resolve_agents_dir(effective_env) / _normalize_agent_id(agent_id)


def resolve_sessions_dir(agent_id: str | None = None, env: dict[str, str] | None = None) -> Path:
    return resolve_agent_dir(agent_id=agent_id, env=env) / "sessions"


def _workspace_from_agents_config(
    *,
    agent_id: str,
    state_dir: Path,
    config: dict[str, Any] | None,
) -> tuple[Path, str]:
    cfg = config if isinstance(config, dict) else {}
    entries = cfg.get("AGENTS_LIST")
    if isinstance(entries, list):
        for item in entries:
            if not isinstance(item, dict):
                continue
            item_id = _normalize_agent_id(str(item.get("id", "")).strip())
            if item_id != agent_id:
                continue
            workspace = item.get("workspace")
            if isinstance(workspace, str) and workspace.strip():
                raw = workspace.strip()
                path = _resolve_workspace_path(raw)
                return path, "agents.list.workspace"

    defaults = cfg.get("AGENTS_DEFAULTS")
    if agent_id == DEFAULT_AGENT_ID and isinstance(defaults, dict):
        workspace = defaults.get("workspace")
        if isinstance(workspace, str) and workspace.strip():
            raw = workspace.strip()
            path = _resolve_workspace_path(raw)
            return path, "agents.defaults.workspace"

    legacy_workspace = cfg.get("WORKSPACE_PATH")
    if agent_id == DEFAULT_AGENT_ID and isinstance(legacy_workspace, str) and legacy_workspace.strip():
        raw = legacy_workspace.strip()
        path = _resolve_workspace_path(raw)
        return path, "legacy.WORKSPACE_PATH"

    if agent_id == DEFAULT_AGENT_ID:
        return (state_dir / "workspace").resolve(), "derived.default"
    return (state_dir / f"workspace-{agent_id}").resolve(), "derived.agent"


def resolve_agent_workspace_dir(
    agent_id: str | None = None,
    *,
    config: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    effective_env = env if env is not None else os.environ
    state_dir = resolve_state_dir(effective_env)
    resolved, _reason = _workspace_from_agents_config(
        agent_id=_normalize_agent_id(agent_id),
        state_dir=state_dir,
        config=config,
    )
    return resolved


def explain_workspace_resolution(
    agent_id: str | None = None,
    *,
    config: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    effective_env = env if env is not None else os.environ
    normalized_agent_id = _normalize_agent_id(agent_id)
    state_dir = resolve_state_dir(effective_env)
    workspace, reason = _workspace_from_agents_config(
        agent_id=normalized_agent_id,
        state_dir=state_dir,
        config=config,
    )
    return {
        "agentId": normalized_agent_id,
        "stateDir": str(state_dir),
        "workspace": str(workspace),
        "decision": reason,
        "configPath": str(resolve_config_path(effective_env)),
        "env": {
            "AURAEVE_STATE_DIR": str(effective_env.get("AURAEVE_STATE_DIR", "")),
            "AURAEVE_CONFIG_PATH": str(effective_env.get("AURAEVE_CONFIG_PATH", "")),
        },
    }


def resolve_vector_db_path(env: dict[str, str] | None = None) -> Path:
    effective_env = env if env is not None else os.environ
    return resolve_state_dir(effective_env) / "memory.db"


def resolve_nodes_dir(env: dict[str, str] | None = None) -> Path:
    effective_env = env if env is not None else os.environ
    return resolve_state_dir(effective_env) / "nodes"


def resolve_cron_dir(env: dict[str, str] | None = None) -> Path:
    effective_env = env if env is not None else os.environ
    return resolve_state_dir(effective_env) / "cron"


def resolve_cron_store_path(env: dict[str, str] | None = None) -> Path:
    effective_env = env if env is not None else os.environ
    return resolve_cron_dir(effective_env) / "cron.json"
