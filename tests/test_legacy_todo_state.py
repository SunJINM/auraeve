from __future__ import annotations

from auraeve.agent.legacy_todo_state import extract_latest_todos


def test_extract_latest_todos_from_transcript_tool_calls() -> None:
    messages = [
        {"role": "user", "content": "开始"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "todo",
                        "arguments": (
                            '{"todos":[{"content":"实现迁移","active_form":"正在实现迁移","status":"in_progress"}]}'
                        ),
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call-1", "name": "todo", "content": "ok"},
    ]

    todos = extract_latest_todos(messages)

    assert todos == [
        {
            "content": "实现迁移",
            "active_form": "正在实现迁移",
            "status": "in_progress",
        }
    ]
