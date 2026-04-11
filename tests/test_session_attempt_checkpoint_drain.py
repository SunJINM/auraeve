from unittest.mock import AsyncMock, MagicMock
from unittest.mock import patch

import pytest

import auraeve.config  # noqa: F401

from auraeve.agent_runtime.session_attempt import SessionAttemptRunner
from auraeve.providers.base import LLMCallError, LLMResponse
from auraeve.providers.base import ToolCallRequest


@pytest.mark.asyncio
async def test_checkpoint_messages_are_injected_before_provider_call() -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=LLMResponse(content="done"))

    tools = MagicMock()
    tools.get_definitions.return_value = []

    hooks = MagicMock()
    hooks.run_before_model_resolve = AsyncMock(return_value=None)

    runner = SessionAttemptRunner(
        provider=provider,
        tools=tools,
        policy=MagicMock(),
        hooks=hooks,
        checkpoint_drain=lambda **_: [{"role": "user", "content": "checkpoint event"}],
    )

    result = await runner.run(
        messages=[{"role": "system", "content": "sys"}],
        model="test-model",
        temperature=0.0,
        max_tokens=256,
        thread_id="webui:s1",
    )

    assert result.final_content == "done"
    sent_messages = provider.chat.await_args.kwargs["messages"]
    assert sent_messages[-1] == {"role": "user", "content": "checkpoint event"}


@pytest.mark.asyncio
async def test_empty_model_response_returns_none_content() -> None:
    """空响应不再抛异常，而是返回 final_content=None（由 kernel 层处理 fallback）。"""
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=LLMResponse(content=None, finish_reason="stop"))

    tools = MagicMock()
    tools.get_definitions.return_value = []

    hooks = MagicMock()
    hooks.run_before_model_resolve = AsyncMock(return_value=None)

    runner = SessionAttemptRunner(
        provider=provider,
        tools=tools,
        policy=MagicMock(),
        hooks=hooks,
    )

    with patch("auraeve.agent_runtime.session_attempt.logger.warning") as warning_mock:
        result = await runner.run(
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "hello"}],
            model="test-model",
            temperature=0.0,
            max_tokens=256,
            thread_id="webui:s1",
        )

    assert result.final_content is None
    warning_mock.assert_called_once()
    warning_message = warning_mock.call_args.args[0]
    assert "finish_reason=stop" in warning_message


@pytest.mark.asyncio
async def test_tool_turn_transition_text_is_preserved_without_runtime_reminder() -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(
        side_effect=[
            LLMResponse(
                content="我先检索公开来源，确认是否有可靠报道。",
                tool_calls=[
                    ToolCallRequest(id="call_1", name="web_search", arguments={"query": "封锁海域"}),
                    ToolCallRequest(id="call_2", name="web_fetch", arguments={"url": "https://example.test"}),
                ],
            ),
            LLMResponse(content="我已经完成初步检索，下一步交叉验证来源。"),
        ]
    )

    tools = MagicMock()
    tools.get_definitions.return_value = [{"type": "function", "function": {"name": "web_search"}}]
    tools.get_metadata.return_value = {}
    tools.get.return_value = None
    tools.execute = AsyncMock(return_value="ok")

    policy_result = MagicMock()
    policy_result.allowed = True
    policy_result.rewritten_args = {}
    policy = MagicMock()
    policy.infer_tool_group.return_value = "network"
    policy.evaluate = AsyncMock(return_value=policy_result)

    hooks = MagicMock()
    hooks.run_before_model_resolve = AsyncMock(return_value=None)
    hooks.run_before_tool_call = AsyncMock(return_value=MagicMock(block=False, params=None))
    hooks.run_after_tool_call = AsyncMock()

    runner = SessionAttemptRunner(
        provider=provider,
        tools=tools,
        policy=policy,
        hooks=hooks,
    )

    result = await runner.run(
        messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "hello"}],
        model="test-model",
        temperature=0.0,
        max_tokens=256,
        thread_id="webui:s1",
    )

    assert result.final_content == "我已经完成初步检索，下一步交叉验证来源。"
    assert result.messages[0]["role"] == "assistant"
    assert result.messages[0]["content"] == "我先检索公开来源，确认是否有可靠报道。"
    second_call_messages = provider.chat.await_args_list[1].kwargs["messages"]
    assert second_call_messages[-3]["role"] == "assistant"
    assert second_call_messages[-3]["content"] == "我先检索公开来源，确认是否有可靠报道。"
    assert second_call_messages[-2]["role"] == "tool"
    assert second_call_messages[-1]["role"] == "tool"


@pytest.mark.asyncio
async def test_tool_only_turn_does_not_inject_progress_reminder() -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(
        side_effect=[
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(id="call_1", name="web_search", arguments={"query": "封锁海域"}),
                    ToolCallRequest(id="call_2", name="web_fetch", arguments={"url": "https://example.test"}),
                ],
            ),
            LLMResponse(content="done"),
        ]
    )

    tools = MagicMock()
    tools.get_definitions.return_value = [{"type": "function", "function": {"name": "web_search"}}]
    tools.get_metadata.return_value = {}
    tools.get.return_value = None
    tools.execute = AsyncMock(return_value="ok")

    policy_result = MagicMock()
    policy_result.allowed = True
    policy_result.rewritten_args = {}
    policy = MagicMock()
    policy.infer_tool_group.return_value = "network"
    policy.evaluate = AsyncMock(return_value=policy_result)

    hooks = MagicMock()
    hooks.run_before_model_resolve = AsyncMock(return_value=None)
    hooks.run_before_tool_call = AsyncMock(return_value=MagicMock(block=False, params=None))
    hooks.run_after_tool_call = AsyncMock()

    runner = SessionAttemptRunner(
        provider=provider,
        tools=tools,
        policy=policy,
        hooks=hooks,
    )

    result = await runner.run(
        messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "hello"}],
        model="test-model",
        temperature=0.0,
        max_tokens=256,
        thread_id="webui:s1",
    )

    assert result.final_content == "done"
    second_call_messages = provider.chat.await_args_list[1].kwargs["messages"]
    assert second_call_messages[-1]["role"] == "tool"
    assert not any(
        message.get("role") == "user" and "阶段性进度" in str(message.get("content") or "")
        for message in second_call_messages
    )
