from __future__ import annotations

from typing import Any

from .manager import get_observability

_SENSITIVE_ATTR_KEYS = {
    "content",
    "fullContent",
    "message",
    "prompt",
    "apiKey",
    "api_key",
    "token",
    "password",
    "secret",
}


def _clean_attr(key: str, value: Any) -> Any:
    if key in _SENSITIVE_ATTR_KEYS:
        text = str(value or "")
        return {"omitted": True, "length": len(text)}
    if isinstance(value, str) and len(value) > 500:
        return f"{value[:500]}...(truncated,{len(value)} chars)"
    return value


def loguru_sink(message: Any) -> None:
    record = message.record
    level = str(record.get("level").name if record.get("level") else "info").lower()
    text = str(record.get("message") or "")
    extra = record.get("extra") or {}
    subsystem = str(extra.get("subsystem") or extra.get("module") or record.get("name") or "app")
    attrs = {
        "function": record.get("function"),
        "line": record.get("line"),
        "file": str(record.get("file").path) if record.get("file") else "",
    }
    if isinstance(extra, dict):
        for key, value in extra.items():
            if key in {"subsystem", "module"}:
                continue
            attrs[key] = _clean_attr(str(key), value)

    try:
        get_observability().emit(
            level=level,
            subsystem=subsystem,
            message=text,
            kind="log",
            attrs=attrs,
        )
    except Exception:
        # Never block the caller on logging failures.
        return
