from unittest.mock import MagicMock
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from auraeve.providers.base import LLMResponse
from auraeve.subagents.fork_context import (
    FORK_DIRECTIVE_PREFIX,
    FORK_PLACEHOLDER_RESULT,
    build_fork_messages,
)
from auraeve.subagents.data.models import Task
from auraeve.subagents.runtime.react_loop import ReActLoop


@pytest.mark.asyncio
async def test_prepare_messages_requires_prompt_assembler():
    loop = ReActLoop(
        provider=MagicMock(),
        tools=MagicMock(),
        policy=MagicMock(),
        model="test-model",
    )
    task = Task(
        task_id="task-fresh",
        goal="分析代码",
    )

    with pytest.raises(ValueError, match="prompt_assembler"):
        await loop._prepare_messages_for_run(task, history_messages=[])  # noqa: SLF001


def test_build_fork_messages_pairs_parent_tool_calls_with_placeholders():
    parent_history = [
        {"role": "user", "content": "请分析认证逻辑"},
        {
            "role": "assistant",
            "content": "我会先搜索相关文件",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "Grep", "arguments": "{\"pattern\":\"auth\"}"},
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "Read", "arguments": "{\"file_path\":\"/repo/auth.py\"}"},
                },
            ],
        },
    ]

    messages = build_fork_messages(parent_history, "继续检查缓存路径")

    assert messages[-3]["role"] == "tool"
    assert messages[-3]["tool_call_id"] == "call_1"
    assert messages[-3]["content"] == FORK_PLACEHOLDER_RESULT
    assert messages[-2]["role"] == "tool"
    assert messages[-2]["tool_call_id"] == "call_2"
    assert messages[-2]["content"] == FORK_PLACEHOLDER_RESULT
    assert messages[-1]["role"] == "user"
    assert FORK_DIRECTIVE_PREFIX in messages[-1]["content"]
    assert "继续检查缓存路径" in messages[-1]["content"]


def test_build_fork_messages_without_tool_calls_still_adds_directive():
    messages = build_fork_messages(
        [{"role": "assistant", "content": "之前的结论"}],
        "检查风险",
    )

    assert messages[-2]["content"] == "之前的结论"
    assert messages[-1]["role"] == "user"
    assert FORK_DIRECTIVE_PREFIX in messages[-1]["content"]


@pytest.mark.asyncio
async def test_subagent_run_uses_prompt_assembler_runtime_messages():
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=LLMResponse(content="完整运行时结果"))

    tools = MagicMock()
    tools.tool_names = ["Read", "Grep"]
    tools.get_definitions.return_value = []

    policy = MagicMock()

    prompt_assembler = MagicMock()
    prompt_assembler.assemble = AsyncMock(
        return_value=SimpleNamespace(
            messages=[
                {"role": "system", "content": "主运行时 system prompt + 子体角色"},
                {"role": "assistant", "content": "之前的结论"},
                {"role": "user", "content": "分析代码"},
            ],
            compacted_messages=None,
            estimated_tokens=100,
        )
    )

    loop = ReActLoop(
        provider=provider,
        tools=tools,
        policy=policy,
        prompt_assembler=prompt_assembler,
        parent_workdir="D:/repo",
        model="test-model",
    )
    task = Task(
        task_id="task-runtime",
        goal="分析代码",
        session_key="sub:task-runtime",
        origin_channel="webui",
        origin_chat_id="chat-1",
    )

    result = await loop.run(
        task,
        history_messages=[{"role": "assistant", "content": "之前的结论"}],
    )

    assert result == "完整运行时结果"
    prompt_assembler.assemble.assert_awaited_once()
    assemble_kwargs = prompt_assembler.assemble.await_args.kwargs
    assert assemble_kwargs["session_id"] == "sub:task-runtime"
    assert assemble_kwargs["messages"] == [{"role": "assistant", "content": "之前的结论"}]
    assert assemble_kwargs["current_query"] == "分析代码"
    assert assemble_kwargs["channel"] == "webui"
    assert assemble_kwargs["chat_id"] == "chat-1"
    assert assemble_kwargs["available_tools"] == {"Read", "Grep"}
    assert assemble_kwargs["prompt_mode"] == "full"
    assert "子智能体类型: general-purpose" in assemble_kwargs["prepend_context"]
    assert "执行预算" in assemble_kwargs["runtime_instruction"]

    provider.chat.assert_awaited_once()
    provider_messages = provider.chat.await_args.kwargs["messages"]
    assert provider_messages[0]["content"] == "主运行时 system prompt + 子体角色"


@pytest.mark.asyncio
async def test_fork_worktree_notice_is_added_to_runtime_instruction():
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=LLMResponse(content="fork result"))

    tools = MagicMock()
    tools.tool_names = ["Read"]
    tools.get_definitions.return_value = []

    policy = MagicMock()

    prompt_assembler = MagicMock()
    prompt_assembler.assemble = AsyncMock(
        return_value=SimpleNamespace(
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "go"},
            ],
            compacted_messages=None,
            estimated_tokens=100,
        )
    )

    loop = ReActLoop(
        provider=provider,
        tools=tools,
        policy=policy,
        prompt_assembler=prompt_assembler,
        model="test-model",
    )
    task = Task(
        task_id="task-worktree",
        goal="检查风险",
        execution_mode="fork",
        context_mode="inherit",
        worktree_path="D:/repo/.worktrees/agent-1234",
    )

    await loop.run(task)

    runtime_instruction = prompt_assembler.assemble.await_args.kwargs["runtime_instruction"]
    current_query = prompt_assembler.assemble.await_args.kwargs["current_query"]
    assert "isolated git worktree" in runtime_instruction
    assert "D:/repo/.worktrees/agent-1234" in runtime_instruction
    assert "Re-read files before editing" in runtime_instruction
    assert FORK_DIRECTIVE_PREFIX in current_query
    assert current_query.strip()
