from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.bus.events import OutboundMessage
from auraeve.subagents.data.models import Task, TaskStatus
from auraeve.subagents.data.repositories import SubagentStore
from auraeve.session.manager import SessionManager
from auraeve.webui.chat_console_service import ChatConsoleService
from auraeve.webui.chat_service import ChatService, RunState
from auraeve.webui.schemas import ChatTranscriptBlockEvent, ChatTranscriptDoneEvent, ChatTranscriptStatusEvent


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
    assert snapshot["summary"]["pendingApprovals"] == 0
    assert snapshot["approvals"] == []
    assert snapshot["timeline"] == []


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
async def test_chat_service_send_does_not_broadcast_run_status_block(tmp_path: Path) -> None:
    queue = RuntimeCommandQueue()
    session_manager = SessionManager(tmp_path / "sessions")
    service = ChatService(session_manager=session_manager, command_queue=queue)
    service._broadcast = AsyncMock()  # type: ignore[method-assign]

    _, status = await service.send(
        session_key="webui:s1",
        message="hello",
        idempotency_key="idem-1",
        user_id="u1",
    )

    assert status == "started"
    service._broadcast.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_chat_service_abort_only_broadcasts_done_event(tmp_path: Path) -> None:
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

    ok, aborted_run_id, status = await service.abort("webui:s1", run_id)
    events = await asyncio.wait_for(events_task, timeout=2)

    assert ok is True
    assert aborted_run_id == run_id
    assert status == "aborted"
    assert events == [
        {
            "type": "transcript.done",
            "sessionKey": "webui:s1",
            "runId": run_id,
            "seq": 0,
        }
    ]


@pytest.mark.asyncio
async def test_chat_service_close_releases_sse_subscribers(tmp_path: Path) -> None:
    queue = RuntimeCommandQueue()
    session_manager = SessionManager(tmp_path / "sessions")
    service = ChatService(session_manager=session_manager, command_queue=queue)

    async def consume() -> list[dict]:
        events: list[dict] = []
        async for event in service.subscribe("webui:s1"):
            events.append(event)
        return events

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)

    await service.close()
    events = await asyncio.wait_for(task, timeout=1)

    assert events == []
    assert service._sse_queues == {}  # noqa: SLF001


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
async def test_chat_service_task_notification_outbound_appends_text_after_completed_run(tmp_path: Path) -> None:
    queue = RuntimeCommandQueue()
    session_manager = SessionManager(tmp_path / "sessions")
    service = ChatService(session_manager=session_manager, command_queue=queue)
    session_key = "webui:s1"
    run_id, _ = await service.send(
        session_key=session_key,
        message="启动同步子体",
        idempotency_key="idem-1",
        user_id="u1",
    )
    service._runs[run_id].assistant_text_emitted = True  # noqa: SLF001
    service._runs[run_id].done = True  # noqa: SLF001

    events_task = asyncio.create_task(_collect_events(service, session_key, expected_count=2))
    await asyncio.sleep(0)

    await service.on_outbound(
        OutboundMessage(
            channel="webui",
            chat_id=session_key,
            content="后台子体完成后的整理结果",
            metadata={"command_mode": "task-notification", "is_meta_event": True},
        )
    )
    events = await asyncio.wait_for(events_task, timeout=2)

    block_event = ChatTranscriptBlockEvent.model_validate(events[0]).model_dump()
    done_event = ChatTranscriptDoneEvent.model_validate(events[1]).model_dump()

    assert block_event["sessionKey"] == session_key
    assert block_event["block"]["type"] == "assistant_text"
    assert block_event["block"]["content"] == "后台子体完成后的整理结果"
    assert done_event["sessionKey"] == session_key


@pytest.mark.asyncio
async def test_system_runtime_delta_creates_system_run_after_completed_user_run(tmp_path: Path) -> None:
    queue = RuntimeCommandQueue()
    session_manager = SessionManager(tmp_path / "sessions")
    service = ChatService(session_manager=session_manager, command_queue=queue)
    session_key = "webui:s1"
    run_id, _ = await service.send(
        session_key=session_key,
        message="启动同步子体",
        idempotency_key="idem-1",
        user_id="u1",
    )
    service._runs[run_id].assistant_text_emitted = True  # noqa: SLF001
    service._runs[run_id].done = True  # noqa: SLF001

    events_task = asyncio.create_task(_collect_events(service, session_key, expected_count=1))
    await asyncio.sleep(0)

    await service._handle_assistant_event(  # noqa: SLF001
        {
            "message": "assistant_text_delta",
            "sessionKey": session_key,
            "attrs": {"delta": "后台结果"},
        }
    )
    events = await asyncio.wait_for(events_task, timeout=2)

    block_event = ChatTranscriptBlockEvent.model_validate(events[0]).model_dump()
    system_run = service._latest_run_for_session(session_key)  # noqa: SLF001

    assert system_run is not None
    assert system_run.run_id != run_id
    assert system_run.kind == "system"
    assert system_run.done is False
    assert block_event["runId"] == system_run.run_id
    assert block_event["block"]["content"] == "后台结果"
    assert block_event["block"]["streaming"] is True


@pytest.mark.asyncio
async def test_system_outbound_after_streaming_only_sends_done(tmp_path: Path) -> None:
    queue = RuntimeCommandQueue()
    session_manager = SessionManager(tmp_path / "sessions")
    service = ChatService(session_manager=session_manager, command_queue=queue)
    session_key = "webui:s1"

    await service._handle_assistant_event(  # noqa: SLF001
        {
            "message": "assistant_text_delta",
            "sessionKey": session_key,
            "attrs": {"delta": "流式"},
        }
    )
    system_run = service._latest_run_for_session(session_key)  # noqa: SLF001
    assert system_run is not None

    events_task = asyncio.create_task(_collect_events(service, session_key, expected_count=1))
    await asyncio.sleep(0)

    await service.on_outbound(
        OutboundMessage(
            channel="webui",
            chat_id=session_key,
            content="流式完整内容",
            metadata={"command_mode": "task-notification", "is_meta_event": True},
        )
    )
    events = await asyncio.wait_for(events_task, timeout=2)

    done_event = ChatTranscriptDoneEvent.model_validate(events[0]).model_dump()
    assert done_event["type"] == "transcript.done"
    assert done_event["runId"] == system_run.run_id
    assert system_run.done is True


@pytest.mark.asyncio
async def test_system_outbound_without_streaming_appends_text_and_done(tmp_path: Path) -> None:
    queue = RuntimeCommandQueue()
    session_manager = SessionManager(tmp_path / "sessions")
    service = ChatService(session_manager=session_manager, command_queue=queue)
    session_key = "webui:s1"

    events_task = asyncio.create_task(_collect_events(service, session_key, expected_count=2))
    await asyncio.sleep(0)

    await service.on_outbound(
        OutboundMessage(
            channel="webui",
            chat_id=session_key,
            content="非流式系统结果",
            metadata={"command_mode": "task-notification", "is_meta_event": True},
        )
    )
    events = await asyncio.wait_for(events_task, timeout=2)

    block_event = ChatTranscriptBlockEvent.model_validate(events[0]).model_dump()
    done_event = ChatTranscriptDoneEvent.model_validate(events[1]).model_dump()

    assert block_event["block"]["content"] == "非流式系统结果"
    assert done_event["type"] == "transcript.done"


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
async def test_chat_service_shows_generate_image_tool_rows(tmp_path: Path) -> None:
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

    await service._handle_tool_event(  # noqa: SLF001
        {
            "message": "tool_call_started",
            "sessionKey": "webui:s1",
            "attrs": {
                "toolName": "generate_image",
                "toolCallId": "call_img",
                "argsPreview": '{"prompt":"狗狗照片"}',
            },
        }
    )

    events = await asyncio.wait_for(events_task, timeout=2)
    block_event = ChatTranscriptBlockEvent.model_validate(events[0]).model_dump()
    assert block_event["runId"] == run_id
    assert block_event["block"]["type"] == "tool_use"
    assert block_event["block"]["toolName"] == "generate_image"
    assert block_event["block"]["arguments"] == {"prompt": "狗狗照片"}


@pytest.mark.asyncio
async def test_chat_service_tool_declared_then_started_then_completed_updates_same_block(tmp_path: Path) -> None:
    queue = RuntimeCommandQueue()
    session_manager = SessionManager(tmp_path / "sessions")
    service = ChatService(session_manager=session_manager, command_queue=queue)
    run_id, _ = await service.send(
        session_key="webui:s1",
        message="hello",
        idempotency_key="idem-1",
        user_id="u1",
    )

    events_task = asyncio.create_task(_collect_events(service, "webui:s1", expected_count=3))
    await asyncio.sleep(0)

    await service._handle_tool_event(  # noqa: SLF001
        {
            "message": "tool_call_declared",
            "sessionKey": "webui:s1",
            "attrs": {
                "toolName": "Bash",
                "toolCallId": "call-1",
                "streamIndex": 0,
            },
        }
    )
    await service._handle_tool_event(  # noqa: SLF001
        {
            "message": "tool_call_started",
            "sessionKey": "webui:s1",
            "attrs": {
                "toolName": "Bash",
                "toolCallId": "call-1",
                "argsPreview": '{"command":"pwd"}',
            },
        }
    )
    await service._handle_tool_event(  # noqa: SLF001
        {
            "message": "tool_call_completed",
            "sessionKey": "webui:s1",
            "attrs": {
                "toolName": "Bash",
                "toolCallId": "call-1",
                "status": "success",
                "argsPreview": '{"command":"pwd"}',
                "resultPreview": "/repo",
            },
        }
    )
    events = await asyncio.wait_for(events_task, timeout=2)

    blocks = [ChatTranscriptBlockEvent.model_validate(event).model_dump()["block"] for event in events]
    assert [block["id"] for block in blocks] == ["tool_use:call-1"] * 3
    assert [block["status"] for block in blocks] == ["preparing", "running", "success"]
    assert events[0]["runId"] == run_id
    assert events[0]["op"] == "append"


@pytest.mark.asyncio
async def test_chat_service_send_starts_obs_listener_before_enqueue(tmp_path: Path) -> None:
    calls: list[str] = []

    class RecordingQueue:
        def enqueue_command(self, command):
            calls.append("enqueue")

    session_manager = SessionManager(tmp_path / "sessions")
    service = ChatService(session_manager=session_manager, command_queue=RecordingQueue())  # type: ignore[arg-type]

    def ensure_listener():
        calls.append("ensure")

    service._ensure_obs_listener = ensure_listener  # type: ignore[method-assign]

    await service.send(
        session_key="webui:s1",
        message="hello",
        idempotency_key="idem-1",
        user_id="u1",
    )

    assert calls == ["ensure", "enqueue"]


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


@pytest.mark.asyncio
async def test_chat_service_compaction_event_broadcasts_compacting_status(tmp_path: Path) -> None:
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

    await service._handle_compaction_event(  # noqa: SLF001
        {
            "message": "context_compacted",
            "sessionKey": "webui:s1",
            "attrs": {
                "tokensBefore": 100000,
                "tokensAfter": 42000,
            },
        }
    )
    events = await asyncio.wait_for(events_task, timeout=2)

    status_event = ChatTranscriptStatusEvent.model_validate(events[0]).model_dump()
    assert status_event == {
        "type": "transcript.status",
        "sessionKey": "webui:s1",
        "runId": run_id,
        "seq": 0,
        "phase": "compacting",
    }


@pytest.mark.asyncio
async def test_chat_service_marks_delta_assistant_text_as_streaming(tmp_path: Path) -> None:
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

    await service._handle_assistant_event(  # noqa: SLF001
        {
            "message": "assistant_text_delta",
            "sessionKey": "webui:s1",
            "attrs": {"delta": "**粗体"},
        }
    )
    await service._handle_assistant_event(  # noqa: SLF001
        {
            "message": "assistant_text",
            "sessionKey": "webui:s1",
            "attrs": {"content": "**粗体**"},
        }
    )
    events = await asyncio.wait_for(events_task, timeout=2)

    delta_event = ChatTranscriptBlockEvent.model_validate(events[0]).model_dump()
    final_event = ChatTranscriptBlockEvent.model_validate(events[1]).model_dump()

    assert delta_event["runId"] == run_id
    assert delta_event["block"]["streaming"] is True
    assert final_event["op"] == "replace"
    assert final_event["block"]["streaming"] is False


@pytest.mark.asyncio
async def test_chat_service_defers_image_placeholder_until_assistant_text(tmp_path: Path) -> None:
    queue = RuntimeCommandQueue()
    session_manager = SessionManager(tmp_path / "sessions")
    service = ChatService(session_manager=session_manager, command_queue=queue)
    run_id, _ = await service.send(
        session_key="webui:s1",
        message="hello",
        idempotency_key="idem-1",
        user_id="u1",
    )

    events_iter = service.subscribe("webui:s1")
    first_event_task = asyncio.create_task(events_iter.__anext__())
    await asyncio.sleep(0)

    await service._handle_image_event(  # noqa: SLF001
        {
            "message": "image_ready",
            "sessionKey": "webui:s1",
            "attrs": {
                "toolCallId": "call_img",
                "prompt": "偏白色版本",
                "size": "1024x1536",
                "images": [{"id": "img_1", "url": "/api/webui/resources/img_1.png", "size": "1024x1536"}],
            },
        }
    )
    await asyncio.sleep(0)

    assert not first_event_task.done()

    await service._handle_assistant_event(  # noqa: SLF001
        {
            "message": "assistant_text_delta",
            "sessionKey": "webui:s1",
            "attrs": {"delta": "改好了，已经调成偏白色版本。"},
        }
    )

    first_event = await asyncio.wait_for(first_event_task, timeout=2)
    second_event = await asyncio.wait_for(events_iter.__anext__(), timeout=2)
    await events_iter.aclose()

    # 图片块先于文本块广播：保证前端在文本铺开前已就位，门控才能在 [[image:N]] 处暂停。
    image_event = ChatTranscriptBlockEvent.model_validate(first_event).model_dump()
    text_event = ChatTranscriptBlockEvent.model_validate(second_event).model_dump()
    assert image_event["block"]["type"] == "image"
    assert image_event["block"]["status"] == "ready"
    assert image_event["block"]["toolCallId"] == "call_img"
    assert text_event["runId"] == run_id
    assert text_event["block"]["type"] == "assistant_text"


@pytest.mark.asyncio
async def test_chat_service_outbound_only_sends_done_after_streamed_assistant_text(tmp_path: Path) -> None:
    queue = RuntimeCommandQueue()
    session_manager = SessionManager(tmp_path / "sessions")
    service = ChatService(session_manager=session_manager, command_queue=queue)
    run_id, _ = await service.send(
        session_key="webui:s1",
        message="hello",
        idempotency_key="idem-1",
        user_id="u1",
    )

    events_task = asyncio.create_task(_collect_events(service, "webui:s1", expected_count=3))
    await asyncio.sleep(0)

    await service._handle_assistant_event(  # noqa: SLF001
        {
            "message": "assistant_text_delta",
            "sessionKey": "webui:s1",
            "attrs": {"delta": "你好"},
        }
    )
    await service._handle_assistant_event(  # noqa: SLF001
        {
            "message": "assistant_text",
            "sessionKey": "webui:s1",
            "attrs": {"content": "你好，世界"},
        }
    )
    await service.on_outbound(
        OutboundMessage(
            channel="webui",
            chat_id="webui:s1",
            content="你好，世界",
            metadata={"run_id": run_id},
        )
    )

    events = await asyncio.wait_for(events_task, timeout=2)
    assert [event["type"] for event in events] == [
        "transcript.block",
        "transcript.block",
        "transcript.done",
    ]
