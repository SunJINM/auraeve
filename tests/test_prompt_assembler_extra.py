import pytest
from unittest.mock import MagicMock

from auraeve.agent_runtime.prompt.assembler import PromptAssembler


def _make_assembler(built_messages):
    builder = MagicMock()
    builder.build_messages = MagicMock(return_value=built_messages)
    assembler = PromptAssembler(context_builder=builder, token_budget=10000)
    return assembler, builder


@pytest.mark.asyncio
async def test_extra_suffix_messages_appended():
    assembler, _builder = _make_assembler([
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ])

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
    assembler, _builder = _make_assembler([
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "hello"},
    ])

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
    original_messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "hello"},
    ]
    assembler, _builder = _make_assembler(original_messages)

    result = await assembler.assemble(
        session_id="s1",
        messages=[],
        current_query="",
        channel="webui",
        chat_id="chat1",
        available_tools=set(),
    )

    assert result.messages == original_messages


@pytest.mark.asyncio
async def test_memory_window_limits_history_passed_to_builder():
    assembler, builder = _make_assembler([
        {"role": "system", "content": "你是助手"},
    ])
    assembler.set_memory_window(2)
    history = [{"role": "user", "content": f"m{i}"} for i in range(5)]

    await assembler.assemble(
        session_id="s1",
        messages=history,
        current_query="now",
        available_tools=set(),
    )

    passed_history = builder.build_messages.call_args.kwargs["history"]
    assert passed_history == history[-2:]
