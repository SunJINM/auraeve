import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from auraeve.subagents.control_plane.orchestrator import TaskOrchestrator
from auraeve.subagents.data.models import Task


def _make_orchestrator():
    orch = object.__new__(TaskOrchestrator)
    orch._bus = MagicMock()
    orch._bus.publish_outbound = AsyncMock()
    orch._kernel_resume_callback = AsyncMock()
    orch._session_locks = {}
    orch._injected_task_ids = set()
    return orch


@pytest.mark.asyncio
async def test_inject_result_to_mother_uses_kernel_resume_callback():
    orch = _make_orchestrator()
    outbound = MagicMock()
    orch._kernel_resume_callback.return_value = outbound

    task = Task(
        task_id="task_1",
        goal="整理分析结论",
        origin_channel="webui",
        origin_chat_id="chat-1",
        spawn_tool_call_id="call_subagent_1",
        agent_name="data_analyst_agent",
    )

    await orch._inject_result_to_mother(task, "最终结论", True)

    orch._kernel_resume_callback.assert_awaited_once()
    _, kwargs = orch._kernel_resume_callback.await_args
    assert kwargs["session_key"] == "webui:chat-1"
    assert kwargs["channel"] == "webui"
    assert kwargs["chat_id"] == "chat-1"
    assert "subagent_result" in json.dumps(kwargs["synthetic_messages"], ensure_ascii=False)
    assert "data_analyst_agent" in json.dumps(kwargs["synthetic_messages"], ensure_ascii=False)
    orch._bus.publish_outbound.assert_awaited_once_with(outbound)


@pytest.mark.asyncio
async def test_inject_result_to_mother_is_idempotent_per_task():
    orch = _make_orchestrator()
    orch._kernel_resume_callback.return_value = None

    task = Task(
        task_id="task_2",
        goal="整理分析结论",
        origin_channel="webui",
        origin_chat_id="chat-1",
    )

    await orch._inject_result_to_mother(task, "第一次结果", True)
    await orch._inject_result_to_mother(task, "第二次结果", True)

    orch._kernel_resume_callback.assert_awaited_once()
    orch._bus.publish_outbound.assert_not_awaited()
