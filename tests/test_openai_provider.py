from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

import auraeve.config  # noqa: F401

from auraeve.providers.base import ContextOverflowError

sys.modules.setdefault("json_repair", types.SimpleNamespace(loads=lambda value: value))

from auraeve.providers.openai_provider import _classify_openai_error
from auraeve.providers.openai_provider import OpenAICompatibleProvider


def test_classify_openai_error_maps_413_to_context_overflow() -> None:
    error = Exception(
        "<html><head><title>413 Request Entity Too Large</title></head><body></body></html>"
    )

    classified = _classify_openai_error(error)

    assert isinstance(classified, ContextOverflowError)


def test_consume_stream_assembles_content() -> None:
    """流式响应正常拼接 content。"""
    provider = object.__new__(OpenAICompatibleProvider)

    async def fake_stream():
        yield SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason=None,
                delta=SimpleNamespace(content="Hello ", reasoning_content=None, tool_calls=None),
            )],
            usage=None,
        )
        yield SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason="stop",
                delta=SimpleNamespace(content="world!", reasoning_content=None, tool_calls=None),
            )],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    result = asyncio.get_event_loop().run_until_complete(
        provider._consume_stream(fake_stream())
    )
    assert result.content == "Hello world!"
    assert result.usage["total_tokens"] == 15


def test_consume_stream_logs_warning_for_empty_response() -> None:
    """流式响应无内容时输出警告。"""
    provider = object.__new__(OpenAICompatibleProvider)

    async def fake_stream():
        yield SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason="stop",
                delta=SimpleNamespace(content=None, reasoning_content=None, tool_calls=None),
            )],
            usage=None,
        )

    with patch("auraeve.providers.openai_provider.logger.warning") as warning_mock:
        result = asyncio.get_event_loop().run_until_complete(
            provider._consume_stream(fake_stream())
        )

    assert result.content is None
    warning_mock.assert_called_once()
    warning_message = warning_mock.call_args.args[0]
    assert "finish_reason=stop" in warning_message


def test_consume_stream_assembles_reasoning_content() -> None:
    """流式响应拼接 reasoning_content。"""
    provider = object.__new__(OpenAICompatibleProvider)

    async def fake_stream():
        yield SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason=None,
                delta=SimpleNamespace(content=None, reasoning_content="thinking...", tool_calls=None),
            )],
            usage=None,
        )
        yield SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason="stop",
                delta=SimpleNamespace(content="answer", reasoning_content=None, tool_calls=None),
            )],
            usage=None,
        )

    result = asyncio.get_event_loop().run_until_complete(
        provider._consume_stream(fake_stream())
    )
    assert result.content == "answer"
    assert result.reasoning_content == "thinking..."
