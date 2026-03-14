from __future__ import annotations

from typing import Any

from .manager import get_observability


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
            attrs[key] = value

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
