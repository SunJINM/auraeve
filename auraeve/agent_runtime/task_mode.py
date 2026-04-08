from __future__ import annotations

import os


_INTERACTIVE_CHANNELS = frozenset({"terminal", "webui"})


def _read_flag(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def is_interactive_channel(channel: str | None) -> bool:
    normalized = str(channel or "").strip().lower()
    return normalized in _INTERACTIVE_CHANNELS


def is_task_v2_enabled(
    *,
    channel: str | None,
    is_subagent: bool = False,
    env: dict[str, str] | None = None,
) -> bool:
    effective_env = env if env is not None else os.environ
    forced = _read_flag(effective_env.get("AURAEVE_ENABLE_TASKS"))
    if forced is not None:
        return forced
    if is_subagent:
        return False
    return is_interactive_channel(channel)
