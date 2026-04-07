from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.agent.tasks import TaskStatus as MainTaskStatus, TaskStore
from auraeve.bus.events import OutboundMessage
from auraeve.subagents.data.models import Task, TaskBudget, TaskStatus
from auraeve.subagents.data.repositories import SubagentStore
from auraeve.session.manager import SessionManager
from auraeve.webui.chat_console_service import ChatConsoleService
from auraeve.webui.chat_service import ChatService, RunState
from auraeve.webui.schemas import ChatTranscriptBlockEvent, ChatTranscriptDoneEvent


async def _collect_events(service: ChatService, session_key: str, expected_count: int) -> list[dict]:
    items: list[dict] = []
    async for event in service.subscribe(session_key):
        items.append(event)
        if len(items) >= expected_count:
            break
    return items

def test_chat_console_snapshot_filters_session_tasks_and_extracts_tools(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    store = SubagentStore(str(tmp_path / "subagent.db"))
    sm = SessionManager(sessions_dir)
    session_key = "webui:test-user"

    session = sm.get_or_create(session_key)
    session.add_message("user", "帮我分析最近的任务状态")
    session.add_message(
        "assistant",
        "",
        tool_calls=[
            {
                "id": "call_sub_1",
                "type": "function",
                "function": {"name": "agent", "arguments": "{\"prompt\":\"分析任务\"}"},
            }
        ],
    )
    session.add_message("tool", "{\"ok\": true}", tool_call_id="call_sub_1", name="agent")
    session.add_message("assistant", "已派出一个子体并等待结果。")
    sm.save(session)

    store.save_task(
        Task(
            task_id="task_1",
            goal="分析任务",
            priority=8,
            status=TaskStatus.RUNNING,
            budget=TaskBudget(),
            origin_channel="webui",
            origin_chat_id=session_key,
        )
    )
    store.save_task(
        Task(
            task_id="task_2",
            goal="不相关任务",
            priority=5,
            status=TaskStatus.COMPLETED,
            budget=TaskBudget(),
            origin_channel="webui",
            origin_chat_id="webui:other-user",
        )
    )

    chat = ChatService(sm, RuntimeCommandQueue())
    chat._runs["run-1"] = RunState(run_id="run-1", session_key=session_key, idempotency_key="ik-1", done=False)

    service = ChatConsoleService(chat_service=chat, store=store)

    snapshot = service.get_snapshot(session_key)

    assert snapshot["run"]["status"] == "running"
    assert snapshot["run"]["runId"] == "run-1"
    assert len(snapshot["tasks"]) == 1
    assert snapshot["tasks"][0]["taskId"] == "task_1"
    assert snapshot["toolCalls"] == []
    assert snapshot["summary"]["runningTasks"] == 1
    assert snapshot["summary"]["runningMainTasks"] == 0
    assert snapshot["summary"]["pendingApprovals"] == 0
    assert snapshot["approvals"] == []
    assert snapshot["nodes"] == []
    assert snapshot["timeline"] == []
    assert snapshot["mainTasks"] == []


def test_chat_console_snapshot_includes_main_thread_task_v2_snapshot(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    task_store = TaskStore(base_dir=tmp_path / "tasks", task_list_id="webui:test-user")
    task_store.create_task(
        subject="梳理运行时模式",
        description="确认交互式与非交互式工具集",
        active_form="正在梳理运行时模式",
    )
    task_store.update_task("1", status=MainTaskStatus.IN_PROGRESS)

    sm = SessionManager(sessions_dir)
    chat = ChatService(sm, RuntimeCommandQueue())
    service = ChatConsoleService(chat_service=chat, store=None, task_base_dir=tmp_path / "tasks")

    snapshot = service.get_snapshot("webui:test-user")

    assert len(snapshot["mainTasks"]) == 1
    assert snapshot["mainTasks"][0]["taskId"] == "1"
    assert snapshot["mainTasks"][0]["status"] == "in_progress"
    assert snapshot["summary"]["runningMainTasks"] == 1
    assert snapshot["toolCalls"] == []


@pytest.mark.asyncio
async def test_chat_service_enqueues_prompt_command(tmp_path: Path) -> None:
    queue = RuntimeCommandQueue()
    sessions_dir = tmp_path / "sessions"
    session_manager = SessionManager(sessions_dir)
    service = ChatService(session_manager=session_manager, command_queue=queue)

    _, status = await service.send(
        session_key="webui:s1",
        message="hello",
        idempotency_key="idem-1",
        user_id="u1",
    )

    assert status == "started"
    commands = queue.snapshot_for_scope(
        max_priority="later",
        agent_id=None,
        is_main_thread=True,
    )
    assert len(commands) == 1
    assert commands[0].mode == "prompt"
    assert commands[0].payload["content"] == "hello"


@pytest.mark.asyncio
async def test_chat_service_send_broadcasts_transcript_run_started_event(tmp_path: Path) -> None:
    queue = RuntimeCommandQueue()
    session_manager = SessionManager(tmp_path / "sessions")
    service = ChatService(session_manager=session_manager, command_queue=queue)

    events_task = asyncio.create_task(_collect_events(service, "webui:s1", expected_count=1))
    await asyncio.sleep(0)

    run_id, status = await service.send(
        session_key="webui:s1",
        message="hello",
        idempotency_key="idem-1",
        user_id="u1",
    )
    events = await asyncio.wait_for(events_task, timeout=2)

    assert status == "started"
    assert len(events) == 1
    event = ChatTranscriptBlockEvent.model_validate(events[0]).model_dump()
    assert event["sessionKey"] == "webui:s1"
    assert event["runId"] == run_id
    assert event["block"]["type"] == "run_status"
    assert event["block"]["status"] == "started"


@pytest.mark.asyncio
async def test_chat_service_on_outbound_broadcasts_assistant_block_and_done(tmp_path: Path) -> None:
    queue = RuntimeCommandQueue()
    session_manager = SessionManager(tmp_path / "sessions")
    service = ChatService(session_manager=session_manager, command_queue=queue)
    run_id, _ = await service.send(
        session_key="webui:s1",
        message="hello",
        idempotency_key="idem-1",
        user_id="u1",
    )

    events_task = asyncio.create_task(_collect_events(service, "webui:s1", expected_count=2))
    await asyncio.sleep(0)

    await service.on_outbound(
        OutboundMessage(
            channel="webui",
            chat_id="webui:s1",
            content="final answer",
            metadata={"run_id": run_id},
        )
    )
    events = await asyncio.wait_for(events_task, timeout=2)

    block_event = ChatTranscriptBlockEvent.model_validate(events[0]).model_dump()
    done_event = ChatTranscriptDoneEvent.model_validate(events[1]).model_dump()

    assert block_event["runId"] == run_id
    assert block_event["block"]["type"] == "assistant_text"
    assert block_event["block"]["content"] == "final answer"
    assert done_event["runId"] == run_id


@pytest.mark.asyncio
async def test_chat_service_tool_completion_keeps_arguments_in_replace_event(tmp_path: Path) -> None:
    queue = RuntimeCommandQueue()
    session_manager = SessionManager(tmp_path / "sessions")
    service = ChatService(session_manager=session_manager, command_queue=queue)
    run_id, _ = await service.send(
        session_key="webui:s1",
        message="hello",
        idempotency_key="idem-1",
        user_id="u1",
    )

    events_task = asyncio.create_task(_collect_events(service, "webui:s1", expected_count=2))
    await asyncio.sleep(0)

    await service._handle_tool_event(  # noqa: SLF001
        {
            "message": "tool_call_started",
            "sessionKey": "webui:s1",
            "attrs": {
                "toolName": "Read",
                "toolCallId": "call-1",
                "argsPreview": '{"file_path":"D:\\\\repo\\\\file.txt"}',
            },
        }
    )
    await service._handle_tool_event(  # noqa: SLF001
        {
            "message": "tool_call_completed",
            "sessionKey": "webui:s1",
            "attrs": {
                "toolName": "Read",
                "toolCallId": "call-1",
                "status": "success",
                "argsPreview": '{"file_path":"D:\\\\repo\\\\file.txt"}',
                "resultPreview": "done",
            },
        }
    )
    events = await asyncio.wait_for(events_task, timeout=2)

    started_event = ChatTranscriptBlockEvent.model_validate(events[0]).model_dump()
    completed_event = ChatTranscriptBlockEvent.model_validate(events[1]).model_dump()

    assert started_event["runId"] == run_id
    assert started_event["block"]["arguments"] == {"file_path": "D:\\repo\\file.txt"}
    assert completed_event["op"] == "replace"
    assert completed_event["block"]["arguments"] == {"file_path": "D:\\repo\\file.txt"}
    assert completed_event["block"]["result"] == "done"


@pytest.mark.asyncio
async def test_chat_service_runtime_assistant_event_broadcasts_assistant_text(tmp_path: Path) -> None:
    queue = RuntimeCommandQueue()
    session_manager = SessionManager(tmp_path / "sessions")
    service = ChatService(session_manager=session_manager, command_queue=queue)
    run_id, _ = await service.send(
        session_key="webui:s1",
        message="hello",
        idempotency_key="idem-1",
        user_id="u1",
    )

    events_task = asyncio.create_task(_collect_events(service, "webui:s1", expected_count=1))
    await asyncio.sleep(0)

    await service._handle_assistant_event(  # noqa: SLF001
        {
            "message": "assistant_text",
            "sessionKey": "webui:s1",
            "attrs": {
                "content": "正在检查 Edit 工具的行为。",
            },
        }
    )
    events = await asyncio.wait_for(events_task, timeout=2)

    block_event = ChatTranscriptBlockEvent.model_validate(events[0]).model_dump()
    assert block_event["runId"] == run_id
    assert block_event["block"]["type"] == "assistant_text"
    assert block_event["block"]["content"] == "正在检查 Edit 工具的行为。"
