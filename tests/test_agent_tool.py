"""AgentTool 入口层测试。"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from auraeve.agent.tools.agent_tool import AgentTool


@pytest.fixture
def agent_tool():
    executor = MagicMock()
    executor.create_task = MagicMock(return_value=MagicMock(
        task_id="abc123",
        goal="测试任务",
        agent_type="general-purpose",
    ))
    executor.execute_async = AsyncMock()
    executor.execute_sync = AsyncMock(return_value="同步执行结果")
    executor.list_tasks = MagicMock(return_value=[])
    executor.get_task = MagicMock(return_value=None)
    executor.cancel_task = MagicMock(return_value=True)
    return AgentTool(executor=executor)


def test_agent_tool_name(agent_tool):
    assert agent_tool.name == "agent"


def test_agent_tool_has_parameters(agent_tool):
    params = agent_tool.parameters
    assert "properties" in params
    assert "prompt" in params["properties"]
    assert "subagent_type" in params["properties"]


@pytest.mark.asyncio
async def test_async_execute(agent_tool):
    result = await agent_tool.execute(
        prompt="分析代码",
        subagent_type="explore",
        run_in_background=True,
    )
    assert "abc123" in result
    agent_tool._executor.execute_async.assert_called_once()


@pytest.mark.asyncio
async def test_sync_execute(agent_tool):
    result = await agent_tool.execute(
        prompt="快速查询",
        run_in_background=False,
    )
    assert result == "同步执行结果"
    agent_tool._executor.execute_sync.assert_called_once()


@pytest.mark.asyncio
async def test_list_tasks(agent_tool):
    result = await agent_tool.execute(action="list")
    assert "没有" in result


@pytest.mark.asyncio
async def test_cancel_task(agent_tool):
    result = await agent_tool.execute(action="cancel", task_id="abc")
    assert "取消" in result
