"""聊天 transcript 投影服务。"""
from __future__ import annotations

import json
import re
from typing import Any


_IMAGE_PLACEHOLDER_RE = re.compile(r"\[\[image(?::[^\]]+)?\]\]")


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
                        "content": _insert_image_placeholders(content, assistant_images),
                        "timestamp": str(message.get("timestamp") or ""),
                    }
                )

            if assistant_images:
                blocks.extend(_image_blocks(f"image:{message_index}", assistant_images))

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
            tool_name = str(message.get("name") or tool_names.get(tool_call_id) or "")

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
                        "toolName": tool_name,
                        "arguments": None,
                        "result": result_content,
                        "status": "error" if is_error else "success",
                        "resources": resources if isinstance(resources, list) else [],
                    }
                )

            # 图片工具产物：从 tool 消息的 images 字段重建 image 块（与实时 SSE 的 id 对齐）
            tool_images = message.get("images") or []
            if tool_images:
                blocks.extend(_image_blocks(f"image:{tool_call_id or message_index}", tool_images))

    # 未回填的 pending 保持 running 状态。
    # 折叠（多个工具合并为汇总列表 / 实时活动行）统一由前端处理，后端只发扁平 tool_use，
    # 确保历史重载与流式输出的折叠行为完全一致。
    return blocks


def _image_blocks(prefix: str, refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """每张图片单独生成一个 image 块。

    历史投影里 assistant / tool 消息可能在 images 字段累积多张图。若合并为单块，
    前端是按「块」消费正文中的 [[image:N]] 标记的——会把多张图全部渲染到第一个标记处、
    后续标记落空。逐张拆块后，[[image:N]] 才能与第 N 张图一一对应。
    """
    out: list[dict[str, Any]] = []
    for index, ref in enumerate(refs):
        if not isinstance(ref, dict):
            continue
        img_id = str(ref.get("id") or "")
        block_id = f"image:{img_id}" if img_id else f"{prefix}:{index}"
        out.append(
            {
                "id": block_id,
                "type": "image",
                "status": "ready",
                "images": [ref],
                "prompt": str(ref.get("prompt") or ""),
                "toolCallId": str(ref.get("toolCallId") or ""),
                "size": str(ref.get("size") or ""),
            }
        )
    return out


def _insert_image_placeholders(content: str, refs: list[dict[str, Any]]) -> str:
    """图片位置由模型用 [[image:资源引用]] 显式标注（资源引用全局唯一，避免序号错乱）。

    若模型已标注则原样保留；未标注（兜底/历史消息）则把各图片的资源引用标记追加到正文末尾，
    不在文本中间猜测位置。
    """
    if not refs or _IMAGE_PLACEHOLDER_RE.search(content):
        return content

    placeholders = "\n".join(f"[[image:{_image_marker(ref)}]]" for ref in refs if isinstance(ref, dict))
    body = content.strip()
    return f"{body}\n\n{placeholders}" if body else placeholders


def _image_marker(ref: dict[str, Any]) -> str:
    """图片的稳定标记：优先资源引用（media://…），回退到资源 id。"""
    return str(ref.get("ref") or ref.get("id") or "")


def _parse_arguments(raw: Any) -> Any:
    if not isinstance(raw, str):
        return raw
    if not raw:
        return ""
    try:
        return json.loads(raw)
    except Exception:
        return raw
