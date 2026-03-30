import pytest
from unittest.mock import MagicMock, AsyncMock
from auraeve.agent_runtime.prompt.assembler import PromptAssembler


def _make_assembler():
    engine = MagicMock()
    hooks = MagicMock()
    hooks.run_before_prompt_build = AsyncMock(return_value=MagicMock(
        prepend_context=None, append_context=None
    ))
    assembler = PromptAssembler(engine=engine, hooks=hooks, token_budget=10000)
    return assembler, engine


@pytest.mark.asyncio
async def test_extra_suffix_messages_appended():
    assembler, engine = _make_assembler()

    engine_result = MagicMock()
    engine_result.messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    engine_result.compacted_messages = None
    engine_result.estimated_tokens = 100
    engine.assemble = AsyncMock(return_value=engine_result)

    extra = [
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "name": "subagent_result", "content": "{}"},
    ]

    result = await assembler.assemble(
        session_id="s1",
        messages=[{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}],
        current_query="",
        channel="webui",
        chat_id="chat1",
        available_tools=set(),
        extra_suffix_messages=extra,
    )

    assert result.messages[-2]["role"] == "assistant"
    assert result.messages[-1]["role"] == "tool"


@pytest.mark.asyncio
async def test_runtime_instruction_injected_into_system():
    assembler, engine = _make_assembler()

    engine_result = MagicMock()
    engine_result.messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "hello"},
    ]
    engine_result.compacted_messages = None
    engine_result.estimated_tokens = 100
    engine.assemble = AsyncMock(return_value=engine_result)

    result = await assembler.assemble(
        session_id="s1",
        messages=[],
        current_query="",
        channel="webui",
        chat_id="chat1",
        available_tools=set(),
        runtime_instruction="直接给出结果，不重复过程。",
    )

    system_content = result.messages[0]["content"]
    assert "[运行时内部约束]" in system_content
    assert "直接给出结果" in system_content


@pytest.mark.asyncio
async def test_no_extra_no_runtime_unchanged():
    assembler, engine = _make_assembler()

    original_messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "hello"},
    ]
    engine_result = MagicMock()
    engine_result.messages = original_messages
    engine_result.compacted_messages = None
    engine_result.estimated_tokens = 50
    engine.assemble = AsyncMock(return_value=engine_result)

    result = await assembler.assemble(
        session_id="s1",
        messages=[],
        current_query="",
        channel="webui",
        chat_id="chat1",
        available_tools=set(),
    )

    assert result.messages == original_messages
