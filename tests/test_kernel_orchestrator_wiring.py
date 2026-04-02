from unittest.mock import AsyncMock, MagicMock

from auraeve.agent.tools.agent_tool import AgentTool
from auraeve.agent.tools.registry import ToolRegistry
from auraeve.agent_runtime.kernel import RuntimeKernel


def test_kernel_registers_resume_callback_on_init():
    kernel = object.__new__(RuntimeKernel)
    kernel._resume_with_subagent_result = AsyncMock()
    kernel._subagent_executor = MagicMock()
    kernel._subagent_executor._kernel_resume_callback = None

    kernel._register_subagent_resume()

    assert kernel._subagent_executor._kernel_resume_callback == kernel._resume_with_subagent_result


def test_set_tool_context_updates_agent_tool_context():
    kernel = object.__new__(RuntimeKernel)
    registry = ToolRegistry()
    tool = AgentTool(executor=MagicMock())
    registry.register(tool)
    kernel.tools = registry

    kernel._set_tool_context("webui", "chat-1", "thread-1")

    assert tool._channel == "webui"
    assert tool._chat_id == "chat-1"
