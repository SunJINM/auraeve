from unittest.mock import AsyncMock, MagicMock

import pytest

from auraeve.agent.tools.subagent_task import SubAgentTaskTool
from auraeve.agent_runtime.kernel import RuntimeKernel
from auraeve.subagents.data.models import Task


def test_kernel_registers_resume_callback_on_init():
    kernel = object.__new__(RuntimeKernel)
    kernel._resume_with_subagent_result = AsyncMock()
    kernel._task_orchestrator = MagicMock()

    kernel._register_subagent_resume()

    kernel._task_orchestrator.register_kernel_resume.assert_called_once_with(
        kernel._resume_with_subagent_result
    )


@pytest.mark.asyncio
async def test_subagent_spawn_passes_agent_name_to_submit_task():
    orchestrator = MagicMock()
    orchestrator.submit_task = AsyncMock(
        return_value=Task(task_id="task_1", goal="分析数据")
    )
    tool = SubAgentTaskTool(orchestrator)
    tool.set_context("webui", "chat-1")

    await tool.execute(
        action="spawn",
        goal="分析数据",
        priority=7,
        assigned_node_id="local",
        agent_name="data_analyst_agent",
    )

    orchestrator.submit_task.assert_awaited_once_with(
        goal="分析数据",
        priority=7,
        origin_channel="webui",
        origin_chat_id="chat-1",
        assigned_node_id="local",
        agent_name="data_analyst_agent",
    )
