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
    TranscriptToolUseBlock,
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


def test_assistant_text_precedes_tool_use_in_same_turn(tmp_path: Path) -> None:
    """同一 assistant 轮次内先叙述、再调用工具时，文本块应排在工具块之前。

    复现 bug：reload 历史后工具块错位到叙述文本上方；流式输出时顺序正常
    （文本 delta 先于工具事件到达）。投影必须与流式顺序一致：text → tool。
    """
    sm = SessionManager(tmp_path / "sessions")
    session = sm.get_or_create("webui:test-user")
    session.add_message("user", "音频内容是啥？")
    session.add_message(
        "assistant",
        "我先直接听一下这段音频，确认它到底在说什么。",
        tool_calls=[
            {
                "id": "read_audio",
                "type": "function",
                "function": {"name": "Read", "arguments": "{\"file_path\":\"audio.m4a\"}"},
            }
        ],
    )
    session.add_message("tool", "大熊猫长得非常可爱。", tool_call_id="read_audio", name="Read")
    session.add_message("assistant", "这段音频在描述大熊猫的外形。")

    blocks = project_history_into_transcript_blocks(session.messages)

    assert [item["type"] for item in blocks] == [
        "user",
        "assistant_text",
        "tool_use",
        "assistant_text",
    ]
    assert blocks[1]["content"].startswith("我先直接听")
    assert blocks[2]["toolName"] == "Read"
    assert blocks[2]["result"] == "大熊猫长得非常可爱。"
    assert blocks[2]["status"] == "success"


def test_generate_image_history_projects_tool_and_image_blocks(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path / "sessions")
    session = sm.get_or_create("webui:test-user")
    session.add_message("user", "生成狗狗照片")
    session.add_message(
        "assistant",
        "我直接给你生成一张偏真实风格的狗狗照片。",
        tool_calls=[
            {
                "id": "call_img",
                "type": "function",
                "function": {"name": "generate_image", "arguments": "{\"prompt\":\"狗狗照片\"}"},
            }
        ],
    )
    session.add_message(
        "tool",
        "已生成 1 张图片。",
        tool_call_id="call_img",
        name="generate_image",
        images=[{"id": "img-1", "url": "/api/webui/resources/img-1/content", "size": "1024x1024"}],
    )

    blocks = project_history_into_transcript_blocks(session.messages)

    assert [item["type"] for item in blocks] == ["user", "assistant_text", "tool_use", "image"]
    assert blocks[2]["toolName"] == "generate_image"
    assert blocks[2]["status"] == "success"
    assert blocks[3]["images"][0]["id"] == "img-1"


def test_assistant_multi_image_projects_one_block_per_image(tmp_path: Path) -> None:
    """assistant 消息累积多张图时，应逐张拆成独立 image 块并保留资源引用，使 [[image:引用]] 能逐张定位。"""
    sm = SessionManager(tmp_path / "sessions")
    session = sm.get_or_create("webui:test-user")
    session.add_message("user", "生成两张有趣的图片")
    session.add_message(
        "assistant",
        "给你两张：\n第一张：月球烤红薯。\n[[image:media://img_a.png]]\n\n第二张：柴犬视频会议。\n[[image:media://img_b.png]]",
        images=[
            {"id": "img_a.png", "ref": "media://img_a.png", "toolCallId": "call_a", "size": "1024x1024"},
            {"id": "img_b.png", "ref": "media://img_b.png", "size": "1024x1024"},
        ],
    )

    blocks = project_history_into_transcript_blocks(session.messages)

    assert [item["type"] for item in blocks] == ["user", "assistant_text", "image", "image"]
    # 每个 image 块只含一张图，且 id 各不相同，[[image:引用]] 才能逐张对应
    assert [len(item["images"]) for item in blocks[2:]] == [1, 1]
    assert blocks[2]["id"] != blocks[3]["id"]
    # 资源引用须透传到 image item，供前端按 ref 精确匹配标记
    assert [item["images"][0]["ref"] for item in blocks[2:]] == ["media://img_a.png", "media://img_b.png"]


def test_unmarked_images_append_ref_based_placeholders(tmp_path: Path) -> None:
    """模型未标注时，兜底在正文末尾追加按资源引用的标记，而非数字序号。"""
    sm = SessionManager(tmp_path / "sessions")
    session = sm.get_or_create("webui:test-user")
    session.add_message("user", "来一张图")
    session.add_message(
        "assistant",
        "这是给你的图：",
        images=[{"id": "img_a.png", "ref": "media://img_a.png", "size": "1024x1024"}],
    )

    blocks = project_history_into_transcript_blocks(session.messages)
    text_block = next(item for item in blocks if item["type"] == "assistant_text")
    assert "[[image:media://img_a.png]]" in text_block["content"]
    assert "[[image:1]]" not in text_block["content"]


def test_readonly_tools_project_as_flat_tool_use_blocks(tmp_path: Path) -> None:
    """后端不再预折叠：连续只读工具投影为扁平 tool_use，折叠交给前端统一处理。"""
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
                "function": {"name": "Read", "arguments": "{\"file_path\":\"config.yaml\"}"},
            }
        ],
    )
    session.add_message("tool", "1\tdb: sqlite", tool_call_id="read_1", name="Read")
    session.add_message(
        "assistant",
        "",
        tool_calls=[
            {
                "id": "read_2",
                "type": "function",
                "function": {"name": "Read", "arguments": "{\"file_path\":\"README.md\"}"},
            }
        ],
    )
    session.add_message("tool", "1\t# AuraEve", tool_call_id="read_2", name="Read")
    session.add_message("assistant", "我已经读取并总结完成。")

    blocks = project_history_into_transcript_blocks(session.messages)

    assert [item["type"] for item in blocks] == ["user", "tool_use", "tool_use", "assistant_text"]
    assert all(isinstance(item.get("id"), str) and item["id"] for item in blocks)
    assert [item["toolName"] for item in blocks[1:3]] == ["Read", "Read"]

    payload = {"sessionKey": "webui:test-user", "blocks": blocks}
    model = ChatTranscriptHistoryResponse.model_validate(payload)
    assert [block.type for block in model.blocks] == ["user", "tool_use", "tool_use", "assistant_text"]


def test_mixed_tools_project_as_flat_tool_use_blocks(tmp_path: Path) -> None:
    """任务类与检索类工具混排时，后端均投影为扁平 tool_use，由前端合并为一个折叠列表。"""
    sm = SessionManager(tmp_path / "sessions")
    session = sm.get_or_create("webui:test-user")
    session.add_message("user", "搜索相关情报")
    session.add_message(
        "assistant",
        "",
        tool_calls=[
            {
                "id": "task_1",
                "type": "function",
                "function": {"name": "TaskCreate", "arguments": "{\"title\":\"调研\"}"},
            }
        ],
    )
    session.add_message("tool", "task created", tool_call_id="task_1", name="TaskCreate")
    session.add_message(
        "assistant",
        "",
        tool_calls=[
            {
                "id": "search_1",
                "type": "function",
                "function": {"name": "web_search", "arguments": "{\"query\":\"封锁海域\"}"},
            }
        ],
    )
    session.add_message("tool", "result 1", tool_call_id="search_1", name="web_search")
    session.add_message(
        "assistant",
        "",
        tool_calls=[
            {
                "id": "fetch_1",
                "type": "function",
                "function": {"name": "web_fetch", "arguments": "{\"url\":\"https://example.test\"}"},
            }
        ],
    )
    session.add_message("tool", "result 2", tool_call_id="fetch_1", name="web_fetch")

    blocks = project_history_into_transcript_blocks(session.messages)

    assert [item["type"] for item in blocks] == ["user", "tool_use", "tool_use", "tool_use"]
    assert [item["toolName"] for item in blocks[1:]] == ["TaskCreate", "web_search", "web_fetch"]


def test_bash_tool_use_projects_as_tool_use(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path / "sessions")
    session = sm.get_or_create("webui:test-user")
    session.add_message("user", "跑一下命令")
    session.add_message(
        "assistant",
        "",
        tool_calls=[
            {
                "id": "bash_1",
                "type": "function",
                "function": {"name": "Bash", "arguments": "{\"command\":\"pwd\"}"},
            }
        ],
    )
    session.add_message("tool", "/d/WorkProjects/auraeve", tool_call_id="bash_1", name="Bash")

    blocks = project_history_into_transcript_blocks(session.messages)

    assert [item["type"] for item in blocks] == ["user", "tool_use"]
    assert blocks[1]["toolName"] == "Bash"


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


def test_tool_use_block_accepts_preparing_status() -> None:
    block = TranscriptToolUseBlock.model_validate(
        {
            "id": "tool_use:call_1",
            "type": "tool_use",
            "toolCallId": "call_1",
            "toolName": "Bash",
            "arguments": {"command": "pwd"},
            "result": None,
            "status": "preparing",
        }
    )

    assert block.status == "preparing"
