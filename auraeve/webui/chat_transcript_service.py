"""聊天 transcript 投影服务。"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


_READONLY_TOOL_NAMES = {"Read", "read", "read_file", "Grep", "Glob"}
_SEARCH_TOOL_NAMES = {"web_search", "web_fetch"}
_COLLAPSIBLE_TOOL_NAMES = _READONLY_TOOL_NAMES | _SEARCH_TOOL_NAMES
_IMAGE_PLACEHOLDER_RE = re.compile(r"\[\[image(?::[^\]]+)?\]\]")
_IMAGE_ANCHOR_WORDS = ("图", "图片", "版本", "效果", "结果", "生成", "完成")
_FOLLOWUP_PREFIXES = ("如果", "还想", "你可以", "可以", "需要", "想要")


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
            # 与流式输出顺序保持一致：同一轮次内叙述文本先于工具调用，
            # 故先投影 assistant_text，再投影 tool_use，避免 reload 后工具块错位到文本上方。
            assistant_images = message.get("images") or []
            content = str(message.get("content") or "")
            if content.strip():
                blocks.append(
                    {
                        "id": f"assistant_text:{message_index}",
                        "type": "assistant_text",
                        "content": _insert_image_placeholders(content, len(assistant_images)),
                        "timestamp": str(message.get("timestamp") or ""),
                    }
                )

            if assistant_images:
                blocks.append(_image_block(f"image:{message_index}", assistant_images))

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
                resources = message.get("resources") or []
                if isinstance(resources, list):
                    blocks[idx]["resources"] = resources
            else:
                # 孤立的 tool_result，创建独立 tool_use
                stable_result_key = tool_call_id or str(message_index)
                resources = message.get("resources") or []
                blocks.append(
                    {
                        "id": f"tool_use:{stable_result_key}",
                        "type": "tool_use",
                        "toolCallId": tool_call_id,
                        "toolName": str(message.get("name") or tool_names.get(tool_call_id) or ""),
                        "arguments": None,
                        "result": result_content,
                        "status": "error" if is_error else "success",
                        "resources": resources if isinstance(resources, list) else [],
                    }
                )

            # 图片工具产物：从 tool 消息的 images 字段重建 image 块（与实时 SSE 的 id 对齐）
            tool_images = message.get("images") or []
            if tool_images:
                blocks.append(_image_block(f"image:{tool_call_id or message_index}", tool_images))

    # 未回填的 pending 保持 running 状态
    return _collapse_readonly_activity(blocks)


def _image_block(block_id: str, refs: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = ""
    size = ""
    if refs and isinstance(refs[0], dict):
        prompt = str(refs[0].get("prompt") or "")
        size = str(refs[0].get("size") or "")
    return {
        "id": block_id,
        "type": "image",
        "status": "ready",
        "images": refs,
        "prompt": prompt,
        "toolCallId": "",
        "size": size,
    }


def _insert_image_placeholders(content: str, image_count: int) -> str:
    if image_count <= 0 or not content.strip() or _IMAGE_PLACEHOLDER_RE.search(content):
        return content

    placeholders = "\n".join(f"[[image:{index}]]" for index in range(1, image_count + 1))
    paragraphs = re.split(r"\n\s*\n", content.strip())
    if not paragraphs:
        return content

    insert_after = 0
    for index, paragraph in enumerate(paragraphs):
        stripped = paragraph.strip()
        if stripped.endswith((":", "：")) and any(word in stripped for word in _IMAGE_ANCHOR_WORDS):
            insert_after = index
            break
    else:
        for index, paragraph in enumerate(paragraphs[1:], start=1):
            stripped = paragraph.strip()
            if stripped.startswith(_FOLLOWUP_PREFIXES):
                insert_after = index - 1
                break

    paragraphs.insert(insert_after + 1, placeholders)
    return "\n\n".join(paragraphs)


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
            activity_type = _activity_type_for_group(group)
            collapsed.append(
                {
                    "id": _build_collapsed_id(activity_type, group),
                    "type": "collapsed_activity",
                    "activityType": activity_type,
                    "count": len(group),
                    "blocks": group,
                }
            )
        else:
            collapsed.extend(group)

    return collapsed


def _is_readonly_block(block: dict[str, Any]) -> bool:
    return block.get("type") == "tool_use" and str(block.get("toolName") or "") in _COLLAPSIBLE_TOOL_NAMES


def _activity_type_for_group(group: list[dict[str, Any]]) -> str:
    tool_names = {str(item.get("toolName") or "") for item in group}
    if tool_names and tool_names <= _SEARCH_TOOL_NAMES:
        return "search"
    return "read"


def _build_collapsed_id(activity_type: str, group: list[dict[str, Any]]) -> str:
    stable_source = "|".join(str(item.get("id") or "") for item in group)
    digest = hashlib.sha1(stable_source.encode("utf-8")).hexdigest()[:12]
    return f"collapsed_activity:{activity_type}:{digest}"
