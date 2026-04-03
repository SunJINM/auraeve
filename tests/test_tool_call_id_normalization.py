from unittest.mock import AsyncMock, MagicMock

import pytest

import auraeve.config  # noqa: F401

from auraeve.agent.tools.base import ToolExecutionResult
from auraeve.agent_runtime.session_attempt import SessionAttemptRunner
from auraeve.providers.base import LLMResponse, ToolCallRequest, normalize_tool_call_ids_in_messages


def test_normalize_tool_call_ids_in_messages_repairs_empty_ids() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":"a.txt"}'},
                },
                {
                    "id": "",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":"b.txt"}'},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "", "name": "read_file", "content": "A"},
        {"role": "tool", "tool_call_id": "", "name": "read_file", "content": "B"},
    ]

    normalized = normalize_tool_call_ids_in_messages(messages)

    first_id = normalized[0]["tool_calls"][0]["id"]
    second_id = normalized[0]["tool_calls"][1]["id"]
    assert first_id
    assert second_id
    assert first_id != second_id
    assert normalized[1]["tool_call_id"] == first_id
    assert normalized[2]["tool_call_id"] == second_id


def test_normalize_tool_call_ids_preserves_structured_tool_content() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_img",
                    "type": "function",
                    "function": {"name": "Read", "arguments": '{"file_path":"C:/tmp/demo.png"}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_img",
            "name": "Read",
            "content": [
                {"type": "text", "text": "Image file: C:/tmp/demo.png"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
            ],
        },
    ]

    normalized = normalize_tool_call_ids_in_messages(messages)

    assert isinstance(normalized[1]["content"], list)
    assert normalized[1]["content"][1]["type"] == "image_url"


@pytest.mark.asyncio
async def test_session_attempt_runner_persists_non_empty_tool_call_ids() -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(
        side_effect=[
            LLMResponse(
                content="need tool",
                tool_calls=[ToolCallRequest(id="", name="search", arguments={"q": "x"})],
            ),
            LLMResponse(content="done"),
        ]
    )

    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.get_metadata.return_value = {}
    tools.execute = AsyncMock(return_value="ok")

    hooks = MagicMock()
    hooks.run_before_model_resolve = AsyncMock(return_value=None)
    hooks.run_before_tool_call = AsyncMock(return_value=MagicMock(block=False, params=None))
    hooks.run_after_tool_call = AsyncMock()

    policy = MagicMock()
    policy.infer_tool_group.return_value = "search"
    policy.evaluate = AsyncMock(return_value=MagicMock(allowed=True, rewritten_args={"q": "x"}, reason=""))

    runner = SessionAttemptRunner(
        provider=provider,
        tools=tools,
        policy=policy,
        hooks=hooks,
        max_iterations=2,
        runtime_execution={"maxTurns": 2, "maxToolCallsTotal": 10, "maxToolCallsPerTurn": 10},
    )

    result = await runner.run(
        messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "go"}],
        model="test-model",
        temperature=0.0,
        max_tokens=256,
        thread_id="webui:s1",
    )

    assert result.final_content == "done"
    assistant_message = result.messages[0]
    tool_message = result.messages[1]
    tool_call_id = assistant_message["tool_calls"][0]["id"]
    assert tool_call_id
    assert tool_message["tool_call_id"] == tool_call_id


@pytest.mark.asyncio
async def test_session_attempt_runner_preserves_structured_tool_results() -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(
        side_effect=[
            LLMResponse(
                content="need tool",
                tool_calls=[ToolCallRequest(id="call_img", name="Read", arguments={"file_path": "C:/tmp/demo.png"})],
            ),
            LLMResponse(content="done"),
        ]
    )

    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.get_metadata.return_value = {}
    tools.execute = AsyncMock(
        return_value=ToolExecutionResult(
            content="Image read successfully: C:/tmp/demo.png",
            extra_messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Image file: C:/tmp/demo.png"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                    ],
                }
            ],
        )
    )

    hooks = MagicMock()
    hooks.run_before_model_resolve = AsyncMock(return_value=None)
    hooks.run_before_tool_call = AsyncMock(return_value=MagicMock(block=False, params=None))
    hooks.run_after_tool_call = AsyncMock()

    policy = MagicMock()
    policy.infer_tool_group.return_value = "filesystem"
    policy.evaluate = AsyncMock(
        return_value=MagicMock(
            allowed=True,
            rewritten_args={"file_path": "C:/tmp/demo.png"},
            reason="",
        )
    )

    runner = SessionAttemptRunner(
        provider=provider,
        tools=tools,
        policy=policy,
        hooks=hooks,
        max_iterations=2,
        runtime_execution={"maxTurns": 2, "maxToolCallsTotal": 10, "maxToolCallsPerTurn": 10},
    )

    result = await runner.run(
        messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "go"}],
        model="test-model",
        temperature=0.0,
        max_tokens=256,
        thread_id="webui:s1",
    )

    assert result.final_content == "done"
    tool_message = result.messages[1]
    assert tool_message["content"] == "Image read successfully: C:/tmp/demo.png"
    second_call_messages = provider.chat.await_args_list[1].kwargs["messages"]
    assert second_call_messages[-1]["role"] == "user"
    assert second_call_messages[-1]["content"][1]["type"] == "image_url"
