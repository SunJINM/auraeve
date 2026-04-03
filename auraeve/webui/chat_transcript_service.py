"""聊天 transcript 投影服务。"""
from __future__ import annotations

import hashlib
import json
from typing import Any


_READONLY_TOOL_NAMES = {"read", "read_file"}


def project_history_into_transcript_blocks(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将历史消息投影为 transcript blocks。"""
    blocks: list[dict[str, Any]] = []
    tool_names: dict[str, str] = {}

    for message_index, message in enumerate(messages):
        role = str(message.get("role") or "")

        if role == "user":
            blocks.append(
                {
                    "id": f"user:{message_index}",
                    "type": "user",
                    "content": str(message.get("content") or ""),
                    "timestamp": str(message.get("timestamp") or ""),
                }
            )
            continue

        if role == "assistant":
            tool_calls = message.get("tool_calls") or []
            for call_index, item in enumerate(tool_calls):
                function = item.get("function") or {}
                tool_call_id = str(item.get("id") or "")
                tool_name = str(function.get("name") or "")
                tool_names[tool_call_id] = tool_name
                stable_call_key = tool_call_id or f"{message_index}:{call_index}"
                blocks.append(
                    {
                        "id": f"tool_call:{stable_call_key}",
                        "type": "tool_call",
                        "toolCallId": tool_call_id,
                        "toolName": tool_name,
                        "arguments": _parse_arguments(function.get("arguments")),
                    }
                )

            content = str(message.get("content") or "")
            if content.strip():
                blocks.append(
                    {
                        "id": f"assistant_text:{message_index}",
                        "type": "assistant_text",
                        "content": content,
                        "timestamp": str(message.get("timestamp") or ""),
                    }
                )
            continue

        if role == "tool":
            tool_call_id = str(message.get("tool_call_id") or "")
            stable_result_key = tool_call_id or str(message_index)
            blocks.append(
                {
                    "id": f"tool_result:{stable_result_key}",
                    "type": "tool_result",
                    "toolCallId": tool_call_id,
                    "toolName": str(message.get("name") or tool_names.get(tool_call_id) or ""),
                    "content": str(message.get("content") or ""),
                }
            )

    return _collapse_readonly_activity(blocks)


def _parse_arguments(raw: Any) -> Any:
    if not isinstance(raw, str):
        return raw
    if not raw:
        return ""
    try:
        return json.loads(raw)
    except Exception:
        return raw


def _collapse_readonly_activity(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    collapsed: list[dict[str, Any]] = []
    cursor = 0

    while cursor < len(blocks):
        if not _is_readonly_block(blocks[cursor]):
            collapsed.append(blocks[cursor])
            cursor += 1
            continue

        start = cursor
        while cursor < len(blocks) and _is_readonly_block(blocks[cursor]):
            cursor += 1
        group = blocks[start:cursor]
        call_count = sum(1 for item in group if item.get("type") == "tool_call")

        if call_count >= 2:
            collapsed.append(
                {
                    "id": _build_collapsed_id("read", group),
                    "type": "collapsed_activity",
                    "activityType": "read",
                    "count": call_count,
                    "blocks": group,
                }
            )
        else:
            collapsed.extend(group)

    return collapsed


def _is_readonly_block(block: dict[str, Any]) -> bool:
    return block.get("type") in {"tool_call", "tool_result"} and str(block.get("toolName") or "") in _READONLY_TOOL_NAMES


def _build_collapsed_id(activity_type: str, group: list[dict[str, Any]]) -> str:
    stable_source = "|".join(str(item.get("id") or "") for item in group)
    digest = hashlib.sha1(stable_source.encode("utf-8")).hexdigest()[:12]
    return f"collapsed_activity:{activity_type}:{digest}"
