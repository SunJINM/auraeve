"""将 OutboundMessage 翻译为 ACP 事件列表。"""
from __future__ import annotations

from typing import Any

from auraeve.bus.events import OutboundMessage


class EventMapper:
    """无状态事件翻译器：OutboundMessage → ACP 事件 dict 列表。"""

    def map(self, msg: OutboundMessage) -> list[dict[str, Any]]:
        acp_event = msg.metadata.get("acp_event")

        if acp_event == "tool_call_started":
            return [{
                "type": "tool_call_started",
                "toolName": msg.metadata.get("tool_name", ""),
                "toolCallId": msg.metadata.get("tool_call_id", ""),
                "input": msg.metadata.get("input", {}),
            }]

        if acp_event == "tool_call_finished":
            return [{
                "type": "tool_call_finished",
                "toolCallId": msg.metadata.get("tool_call_id", ""),
                "result": msg.content,
            }]

        if acp_event == "done":
            return [{
                "type": "done",
                "stopReason": msg.metadata.get("stop_reason", "stop"),
            }]

        if acp_event == "usage_update":
            return [{
                "type": "usage_update",
                "inputTokens": msg.metadata.get("input_tokens", 0),
                "outputTokens": msg.metadata.get("output_tokens", 0),
            }]

        # 普通文本 → message_chunk (仅当未指定 acp_event 时)
        if acp_event is None and msg.content:
            return [{"type": "message_chunk", "text": msg.content}]

        return []
