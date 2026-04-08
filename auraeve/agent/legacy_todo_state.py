from __future__ import annotations

import json
from typing import Any


def extract_latest_todos(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for tool_call in message.get("tool_calls") or []:
            function = tool_call.get("function") or {}
            if function.get("name") != "todo":
                continue
            raw_arguments = function.get("arguments")
            if not isinstance(raw_arguments, str) or not raw_arguments.strip():
                continue
            try:
                payload = json.loads(raw_arguments)
            except Exception:
                continue
            todos = payload.get("todos")
            if isinstance(todos, list):
                latest = [dict(item) for item in todos if isinstance(item, dict)]
    return latest
