from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from auraeve.session.manager import SessionManager
from auraeve.webui.chat_transcript_service import project_history_into_transcript_blocks
from auraeve.webui.schemas import (
    ChatTranscriptBlockEvent,
    ChatTranscriptDoneEvent,
    ChatTranscriptHistoryResponse,
    TranscriptCollapsedActivityBlock,
)


def test_project_history_into_transcript_blocks(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path / "sessions")
    session = sm.get_or_create("webui:test-user")
    session.add_message("user", "帮我看一下项目进度")
    session.add_message(
        "assistant",
        "",
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "agent", "arguments": "{\"prompt\":\"分析任务\"}"},
            }
        ],
    )
    session.add_message("tool", "{\"ok\": true}", tool_call_id="call_1", name="agent")
    session.add_message("assistant", "任务已经分析完成。")

    blocks = project_history_into_transcript_blocks(session.messages)

    # tool_call + tool_result 合并为单个 tool_use
    assert [item["type"] for item in blocks] == [
        "user",
        "tool_use",
        "assistant_text",
    ]
    assert all(isinstance(item.get("id"), str) and item["id"] for item in blocks)
    # tool_use 应包含 result 和 status
    tool_use = blocks[1]
    assert tool_use["status"] == "success"
    assert tool_use["result"] == '{"ok": true}'

    blocks_again = project_history_into_transcript_blocks(session.messages)
    assert [item["id"] for item in blocks] == [item["id"] for item in blocks_again]


def test_collapse_readonly_activity_into_single_block(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path / "sessions")
    session = sm.get_or_create("webui:test-user")
    session.add_message("user", "读一下配置文件和 README")
    session.add_message(
        "assistant",
        "",
        tool_calls=[
            {
                "id": "read_1",
                "type": "function",
                "function": {"name": "read", "arguments": "{\"path\":\"config.yaml\"}"},
            }
        ],
    )
    session.add_message("tool", "db: sqlite", tool_call_id="read_1", name="read")
    session.add_message(
        "assistant",
        "",
        tool_calls=[
            {
                "id": "read_2",
                "type": "function",
                "function": {"name": "read", "arguments": "{\"path\":\"README.md\"}"},
            }
        ],
    )
    session.add_message("tool", "# AuraEve", tool_call_id="read_2", name="read")
    session.add_message("assistant", "我已经读取并总结完成。")

    blocks = project_history_into_transcript_blocks(session.messages)

    assert [item["type"] for item in blocks] == ["user", "collapsed_activity", "assistant_text"]
    assert all(isinstance(item.get("id"), str) and item["id"] for item in blocks)
    assert blocks[1]["activityType"] == "read"
    assert blocks[1]["count"] == 2
    # 折叠块内部现在是 tool_use 类型
    assert [item["type"] for item in blocks[1]["blocks"]] == [
        "tool_use",
        "tool_use",
    ]
    assert all(isinstance(item.get("id"), str) and item["id"] for item in blocks[1]["blocks"])

    payload = {"sessionKey": "webui:test-user", "blocks": blocks}
    model = ChatTranscriptHistoryResponse.model_validate(payload)
    assert model.blocks[1].type == "collapsed_activity"


def test_chat_transcript_event_schema_requires_valid_block_states() -> None:
    ChatTranscriptBlockEvent.model_validate(
        {
            "type": "transcript.block",
            "sessionKey": "webui:test",
            "seq": 1,
            "op": "append",
            "block": {
                "id": "user:1",
                "type": "user",
                "content": "hello",
                "timestamp": "2026-04-03T00:00:00",
            },
        }
    )
    ChatTranscriptDoneEvent.model_validate(
        {
            "type": "transcript.done",
            "sessionKey": "webui:test",
            "seq": 2,
        }
    )

    with pytest.raises(ValidationError):
        ChatTranscriptBlockEvent.model_validate(
            {
                "type": "transcript.block",
                "sessionKey": "webui:test",
                "seq": 3,
                "op": "append",
            }
        )

    with pytest.raises(ValidationError):
        ChatTranscriptDoneEvent.model_validate(
            {
                "type": "transcript.done",
                "sessionKey": "webui:test",
                "seq": 4,
                "block": {
                    "id": "assistant:1",
                    "type": "assistant_text",
                    "content": "ok",
                    "timestamp": "2026-04-03T00:00:00",
                },
            }
        )


def test_collapsed_activity_nested_blocks_require_structured_items() -> None:
    TranscriptCollapsedActivityBlock.model_validate(
        {
            "id": "collapsed:read:1",
            "type": "collapsed_activity",
            "activityType": "read",
            "count": 1,
            "blocks": [
                {
                    "id": "tool_use:1",
                    "type": "tool_use",
                    "toolCallId": "call_1",
                    "toolName": "read",
                    "arguments": {"path": "README.md"},
                    "result": "content",
                    "status": "success",
                }
            ],
        }
    )

    with pytest.raises(ValidationError):
        TranscriptCollapsedActivityBlock.model_validate(
            {
                "id": "collapsed:read:2",
                "type": "collapsed_activity",
                "activityType": "read",
                "count": 1,
                "blocks": [
                    {
                        "type": "tool_use",
                        "toolName": "read",
                        "arguments": {"path": "README.md"},
                    }
                ],
            }
        )
