"""Mapping helpers for ACP development sessions."""

from __future__ import annotations


def _escape_key_part(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")


def build_dev_session_key(agent_id: str, workspace_id: str, thread_id: str) -> str:
    return "dev:" + ":".join(
        _escape_key_part(part)
        for part in (agent_id, workspace_id, thread_id)
    )
