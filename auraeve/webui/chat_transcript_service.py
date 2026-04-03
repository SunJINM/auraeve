"""聊天 transcript 投影服务。"""
from __future__ import annotations

import hashlib
import json
from typing import Any


_READONLY_TOOL_NAMES = {"Read", "read", "read_file", "grep", "glob", "bash"}


def project_history_into_transcript_blocks(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将历史消息投影为 transcript blocks，tool_call + tool_result 合并为 tool_use。"""
    blocks: list[dict[str, Any]] = []
    # toolCallId -> tool_use block 的索引，用于回填 result
    pending_tool_uses: dict[str, int] = {}
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
                block_id = f"tool_use:{stable_call_key}"
                block = {
                    "id": block_id,
                    "type": "tool_use",
                    "toolCallId": tool_call_id,
                    "toolName": tool_name,
                    "arguments": _parse_arguments(function.get("arguments")),
                    "result": None,
                    "status": "running",
                }
                pending_tool_uses[tool_call_id] = len(blocks)
                blocks.append(block)

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
            result_content = str(message.get("content") or "")
            is_error = "error" in result_content.lower()[:100] if result_content else False

            # 回填到已有的 tool_use block
            if tool_call_id in pending_tool_uses:
                idx = pending_tool_uses.pop(tool_call_id)
                blocks[idx]["result"] = result_content
                blocks[idx]["status"] = "error" if is_error else "success"
            else:
                # 孤立的 tool_result，创建独立 tool_use
                stable_result_key = tool_call_id or str(message_index)
                blocks.append(
                    {
                        "id": f"tool_use:{stable_result_key}",
                        "type": "tool_use",
                        "toolCallId": tool_call_id,
                        "toolName": str(message.get("name") or tool_names.get(tool_call_id) or ""),
                        "arguments": None,
                        "result": result_content,
                        "status": "error" if is_error else "success",
                    }
                )

    # 未回填的 pending 保持 running 状态
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

        if len(group) >= 2:
            collapsed.append(
                {
                    "id": _build_collapsed_id("read", group),
                    "type": "collapsed_activity",
                    "activityType": "read",
                    "count": len(group),
                    "blocks": group,
                }
            )
        else:
            collapsed.extend(group)

    return collapsed


def _is_readonly_block(block: dict[str, Any]) -> bool:
    return block.get("type") == "tool_use" and str(block.get("toolName") or "") in _READONLY_TOOL_NAMES


def _build_collapsed_id(activity_type: str, group: list[dict[str, Any]]) -> str:
    stable_source = "|".join(str(item.get("id") or "") for item in group)
    digest = hashlib.sha1(stable_source.encode("utf-8")).hexdigest()[:12]
    return f"collapsed_activity:{activity_type}:{digest}"
