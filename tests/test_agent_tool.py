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
        execution_mode="sync",
    ))
    executor.execute_async = AsyncMock()
    executor.execute_sync = AsyncMock(return_value="同步执行结果")
    executor.continue_task = AsyncMock(return_value="已继续子智能体 abc123")
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
    assert "execution_mode" in params["properties"]


@pytest.mark.asyncio
async def test_async_execute(agent_tool):
    result = await agent_tool.execute(
        prompt="分析代码",
        subagent_type="explore",
        execution_mode="async",
    )
    assert "abc123" in result
    agent_tool._executor.execute_async.assert_called_once()


@pytest.mark.asyncio
async def test_sync_execute(agent_tool):
    result = await agent_tool.execute(
        prompt="快速查询",
        execution_mode="sync",
    )
    assert result == "同步执行结果"
    agent_tool._executor.execute_sync.assert_called_once()


@pytest.mark.asyncio
async def test_fork_execute_creates_inherit_task(agent_tool):
    await agent_tool.execute(
        prompt="检查刚才讨论的改动风险",
        execution_mode="fork",
    )
    call = agent_tool._executor.create_task.call_args.kwargs
    assert call["execution_mode"] == "fork"
    assert call["context_mode"] == "inherit"


@pytest.mark.asyncio
async def test_run_in_background_compat_maps_to_async(agent_tool):
    await agent_tool.execute(
        prompt="后台收集信息",
        run_in_background=True,
    )
    call = agent_tool._executor.create_task.call_args.kwargs
    assert call["execution_mode"] == "async"


@pytest.mark.asyncio
async def test_continue_task(agent_tool):
    result = await agent_tool.execute(
        action="continue",
        task_id="abc123",
        prompt="基于刚才的发现继续修复",
    )
    assert "继续" in result
    agent_tool._executor.continue_task.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_tasks(agent_tool):
    result = await agent_tool.execute(action="list")
    assert "没有" in result


@pytest.mark.asyncio
async def test_cancel_task(agent_tool):
    result = await agent_tool.execute(action="cancel", task_id="abc")
    assert "取消" in result
