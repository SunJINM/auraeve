from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

from fastapi.testclient import TestClient

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.agent.tasks import TaskStore
from auraeve.session.manager import SessionManager
from auraeve.webui.chat_service import ChatService
from auraeve.webui.server import WebUIServer


class _StubChatService:
    def get_history(self, session_key: str, limit: int = 200) -> list[dict]:
        return []

    def get_runtime_status(self, session_key: str) -> dict:
        return {"runId": "run-1", "status": "running", "done": False, "aborted": False}

    async def send(
        self,
        session_key: str,
        message: str,
        idempotency_key: str,
        user_id: str,
        display_name: str | None = None,
    ) -> tuple[str, str]:
        return "run-1", "started"

    async def abort(self, session_key: str, run_id: str | None = None) -> tuple[bool, str | None, str]:
        return True, "run-1", "aborted"

    async def subscribe(self, session_key: str):
        yield {"type": "transcript.done", "sessionKey": session_key, "runId": "run-1", "seq": 1}


def _build_server(chat_service, workspace: Path) -> TestClient:
    server = WebUIServer(
        chat_service=chat_service,
        config_service=MagicMock(),
        token="secret",
        workspace=workspace,
    )
    return TestClient(server._app)


def test_chat_transcript_route_returns_blocks_and_run_state(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    session_manager = SessionManager(tmp_path / "sessions")
    session = session_manager.get_or_create("webui:test")
    session.add_message("user", "hello")
    session.add_message("assistant", "world")
    session_manager.save(session)

    chat = ChatService(session_manager=session_manager, command_queue=RuntimeCommandQueue())
    client = _build_server(chat, workspace=workspace)

    response = client.get(
        "/api/webui/chat/transcript",
        params={"sessionKey": "webui:test"},
        headers={"X-WEBUI-TOKEN": "secret"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["sessionKey"] == "webui:test"
    assert payload["run"]["status"] == "idle"
    assert [item["type"] for item in payload["blocks"]] == ["user", "assistant_text"]


def test_chat_transcript_events_route_streams_transcript_events(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    client = _build_server(_StubChatService(), workspace=workspace)

    with client.stream(
        "GET",
        "/api/webui/chat/transcript/events",
        params={"sessionKey": "webui:test"},
        headers={"X-WEBUI-TOKEN": "secret"},
    ) as response:
        assert response.status_code == 200
        first_line = ""
        for line in response.iter_lines():
            if line:
                first_line = line
                break

    assert first_line.startswith("data: ")
    event = json.loads(first_line[6:])
    assert event["type"] == "transcript.done"
    assert event["sessionKey"] == "webui:test"


def test_chat_runtime_route_reads_main_tasks_from_state_tasks_dir(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    state_dir = tmp_path / ".auraeve"
    sessions_dir = state_dir / "agents" / "default" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    task_store = TaskStore(base_dir=state_dir / "tasks", task_list_id="webui:test")
    task_store.create_task(
        subject="验证实时任务卡片",
        description="确认 chat/runtime 会返回主线程任务",
        active_form="正在验证实时任务卡片",
    )

    chat = ChatService(session_manager=SessionManager(sessions_dir), command_queue=RuntimeCommandQueue())
    with patch("auraeve.webui.server.cfg.resolve_state_dir", return_value=state_dir):
        client = _build_server(chat, workspace=workspace)

    response = client.get(
        "/api/webui/chat/runtime",
        params={"sessionKey": "webui:test"},
        headers={"X-WEBUI-TOKEN": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["mainTasks"]) == 1
    assert payload["mainTasks"][0]["subject"] == "验证实时任务卡片"
