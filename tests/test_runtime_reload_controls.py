from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from auraeve.agent_runtime.kernel import RuntimeKernel
from auraeve.agent_runtime.tool_policy.contracts import PolicyContext
from auraeve.agent_runtime.tool_policy.engine import ToolPolicyEngine


@pytest.mark.asyncio
async def test_kernel_reload_delegates_to_component_runtime_interfaces() -> None:
    kernel = object.__new__(RuntimeKernel)
    kernel._reload_lock = asyncio.Lock()
    kernel.temperature = 0.0
    kernel.max_tokens = 1000
    kernel.max_iterations = 20
    kernel.assembler = MagicMock()
    kernel.policy = MagicMock()
    kernel._runner = MagicMock()
    kernel._orchestrator = MagicMock()

    result = await RuntimeKernel.reload_runtime_config(
        kernel,
        {
            "LLM_TEMPERATURE": 0.3,
            "LLM_MAX_TOKENS": 2000,
            "LLM_MAX_TOOL_ITERATIONS": 9,
            "RUNTIME_LOOP_GUARD": {"onRepeat": "block"},
            "LLM_MEMORY_WINDOW": 12,
            "TOKEN_BUDGET": 60_000,
            "GLOBAL_DENY_TOOLS": ["Bash"],
            "SESSION_TOOL_POLICY": {"webui": {"deny": ["Write"]}},
        },
    )

    assert result == {
        "applied": [
            "LLM_TEMPERATURE",
            "LLM_MAX_TOKENS",
            "LLM_MAX_TOOL_ITERATIONS",
            "RUNTIME_LOOP_GUARD",
            "LLM_MEMORY_WINDOW",
            "GLOBAL_DENY_TOOLS",
            "SESSION_TOOL_POLICY",
            "TOKEN_BUDGET",
        ],
        "requiresRestart": [],
        "issues": [],
    }
    assert kernel.temperature == 0.3
    assert kernel.max_tokens == 2000
    assert kernel.max_iterations == 9
    kernel.assembler.apply_runtime_controls.assert_has_calls(
        [
            call(memory_window=12),
            call(token_budget=60_000),
        ]
    )
    kernel.policy.apply_runtime_policy.assert_has_calls(
        [
            call(global_deny=["Bash"]),
            call(session_policy={"webui": {"deny": ["Write"]}}),
        ]
    )
    kernel._runner.apply_runtime_controls.assert_has_calls(
        [
            call(max_iterations=9),
            call(runtime_loop_guard={"onRepeat": "block"}),
            call(token_budget=60_000),
        ]
    )
    kernel._orchestrator.apply_runtime_controls.assert_called_once_with(token_budget=60_000)


@pytest.mark.asyncio
async def test_kernel_reload_llm_models_replaces_live_provider_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    kernel = object.__new__(RuntimeKernel)
    kernel._reload_lock = asyncio.Lock()
    kernel.provider = SimpleNamespace(name="old-provider")
    kernel.model = "gpt-4o-mini"
    kernel.temperature = 0.7
    kernel.max_tokens = 8192
    kernel.thinking_budget_tokens = None
    kernel._runner = MagicMock()
    kernel._orchestrator = MagicMock()
    kernel._subagent_executor = MagicMock()
    kernel._register_default_tools = MagicMock()
    new_provider = SimpleNamespace(name="new-provider")
    llm_models = [
        {
            "id": "main",
            "label": "主模型",
            "enabled": True,
            "isPrimary": True,
            "model": "gpt-4.1-mini",
            "apiBase": "https://api.example.com/v1",
            "apiKey": "sk-test",
            "extraHeaders": {},
            "maxTokens": 4096,
            "temperature": 0.2,
            "thinkingBudgetTokens": 128,
            "capabilities": {
                "imageInput": True,
                "audioInput": False,
                "documentInput": True,
                "toolCalling": True,
                "streaming": True,
            },
        }
    ]

    fake_openai_provider = types.ModuleType("auraeve.providers.openai_provider")
    fake_openai_provider.build_openai_provider_from_model_card = MagicMock(return_value=new_provider)
    monkeypatch.setitem(sys.modules, "auraeve.providers.openai_provider", fake_openai_provider)

    result = await RuntimeKernel.reload_runtime_config(kernel, {"LLM_MODELS": llm_models})

    assert result == {"applied": ["LLM_MODELS"], "requiresRestart": [], "issues": []}
    assert kernel.provider is new_provider
    assert kernel.model == "gpt-4.1-mini"
    assert kernel.temperature == 0.2
    assert kernel.max_tokens == 4096
    assert kernel.thinking_budget_tokens == 128
    assert kernel._runner._provider is new_provider
    assert kernel._runner._thinking_budget_tokens == 128
    assert kernel._orchestrator._provider is new_provider
    assert kernel._subagent_executor._provider is new_provider
    assert kernel._subagent_executor._model == "gpt-4.1-mini"
    kernel._register_default_tools.assert_called_once()


@pytest.mark.asyncio
async def test_tool_policy_runtime_update_replaces_policy_sets() -> None:
    policy = ToolPolicyEngine(global_deny={"Write"})
    policy.apply_runtime_policy(
        global_deny=["Bash"],
        session_policy={"webui": {"deny": ["Read"]}},
    )

    bash = await policy.evaluate(
        PolicyContext(
            tool_name="Bash",
            args={},
            session_id="webui:chat-1",
            channel="webui",
            chat_id="chat-1",
        )
    )
    write = await policy.evaluate(
        PolicyContext(
            tool_name="Write",
            args={},
            session_id="webui:chat-1",
            channel="webui",
            chat_id="chat-1",
        )
    )
    read = await policy.evaluate(
        PolicyContext(
            tool_name="Read",
            args={},
            session_id="webui:chat-1",
            channel="webui",
            chat_id="chat-1",
        )
    )

    assert bash.allowed is False
    assert write.allowed is True
    assert read.allowed is False
