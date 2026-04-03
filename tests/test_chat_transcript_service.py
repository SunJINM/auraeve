from __future__ import annotations

from pathlib import Path

from auraeve.session.manager import SessionManager
from auraeve.webui.chat_transcript_service import project_history_into_transcript_blocks


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

    assert [item["type"] for item in blocks] == [
        "user",
        "tool_call",
        "tool_result",
        "assistant_text",
    ]


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
    assert blocks[1]["activityType"] == "read"
    assert blocks[1]["count"] == 2
