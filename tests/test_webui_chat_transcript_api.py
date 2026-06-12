from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from datetime import timedelta

from fastapi.testclient import TestClient

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.agent.tasks import TaskStore
from auraeve.session.manager import SessionManager
from auraeve.webui.chat_service import ChatService
from auraeve.webui.server import WebUIServer, test_setup_model as run_setup_model_probe


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


class _RuntimeAwareStubChatService(_StubChatService):
    def __init__(self) -> None:
        self.applied_configs: list[dict] = []

    async def apply_runtime_config(self, config: dict) -> dict:
        self.applied_configs.append(config)
        return {"applied": list(config.keys()), "requiresRestart": [], "issues": []}


def _build_server(chat_service) -> TestClient:
    server = WebUIServer(
        chat_service=chat_service,
        token="secret",
    )
    return TestClient(server._app)


def test_webui_server_start_uses_embedded_uvicorn_without_signal_capture(tmp_path: Path) -> None:
    calls: list[str] = []

    class _FakeServer:
        def __init__(self, config):
            self.config = config
            self.should_exit = False

        async def serve(self):
            calls.append("serve")

        async def _serve(self):
            calls.append("_serve")

    server = WebUIServer(
        chat_service=_StubChatService(),
        token="secret",
    )

    with patch("auraeve.webui.server.uvicorn.Config", return_value=SimpleNamespace()), patch(
        "auraeve.webui.server.uvicorn.Server",
        _FakeServer,
    ):
        import asyncio

        asyncio.run(server.start())

    assert calls == ["_serve"]


def test_chat_transcript_route_returns_blocks_and_run_state(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path / "sessions")
    session = session_manager.get_or_create("webui:test")
    session.add_message("user", "hello")
    session.add_message("assistant", "world")
    session_manager.save(session)

    chat = ChatService(session_manager=session_manager, command_queue=RuntimeCommandQueue())
    client = _build_server(chat)

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
    client = _build_server(_StubChatService())

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
        client = _build_server(chat)

    response = client.get(
        "/api/webui/chat/runtime",
        params={"sessionKey": "webui:test"},
        headers={"X-WEBUI-TOKEN": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["mainTasks"]) == 1
    assert payload["mainTasks"][0]["subject"] == "验证实时任务卡片"


def test_chat_sessions_route_lists_backend_sessions_by_updated_time(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path / "sessions")
    first = session_manager.get_or_create("webui:first")
    first.metadata["title"] = "第一段对话"
    first.add_message("user", "旧问题")
    first.updated_at = first.updated_at - timedelta(minutes=1)
    session_manager.save(first)
    second = session_manager.get_or_create("webui:second")
    second.metadata["title"] = "第二段对话"
    second.add_message("user", "新问题")
    session_manager.save(second)

    chat = ChatService(session_manager=session_manager, command_queue=RuntimeCommandQueue())
    client = _build_server(chat)

    response = client.get(
        "/api/webui/chat/sessions",
        headers={"X-WEBUI-TOKEN": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["key"] for item in payload["sessions"]] == ["webui:second", "webui:first"]
    assert payload["sessions"][0]["title"] == "第二段对话"


def test_chat_sessions_create_and_delete_are_persisted_in_backend(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path / "sessions")
    chat = ChatService(session_manager=session_manager, command_queue=RuntimeCommandQueue())
    client = _build_server(chat)

    created = client.post(
        "/api/webui/chat/sessions",
        headers={"X-WEBUI-TOKEN": "secret"},
    )

    assert created.status_code == 200
    session_key = created.json()["session"]["key"]
    assert session_manager._get_session_path(session_key).exists()

    deleted = client.delete(
        f"/api/webui/chat/sessions/{session_key}",
        headers={"X-WEBUI-TOKEN": "secret"},
    )

    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    assert not session_manager._get_session_path(session_key).exists()


def test_setup_status_reports_missing_primary_model_key_without_leaking_secret() -> None:
    client = _build_server(_StubChatService())
    config = {
        "LLM_MODELS": [
            {
                "id": "main",
                "label": "主模型",
                "enabled": True,
                "isPrimary": True,
                "model": "gpt-4o-mini",
                "apiBase": None,
                "apiKey": "",
            }
        ]
    }

    with patch("auraeve.webui.server.cfg.export_config", return_value=config):
        response = client.get(
            "/api/webui/setup/status",
            headers={"X-WEBUI-TOKEN": "secret"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is False
    assert payload["model"] == "gpt-4o-mini"
    assert "apiKey" not in payload


def test_setup_models_fetches_available_models_from_candidate_credentials() -> None:
    client = _build_server(_StubChatService())
    fetch_models = AsyncMock(return_value=["gpt-4.1-mini", "gpt-4o-mini"])

    with patch("auraeve.webui.server.fetch_setup_models", fetch_models, create=True):
        response = client.post(
            "/api/webui/setup/models",
            headers={"X-WEBUI-TOKEN": "secret"},
            json={"apiBase": "https://api.example.com/v1", "apiKey": "sk-test"},
        )

    assert response.status_code == 200
    assert response.json() == {"models": ["gpt-4.1-mini", "gpt-4o-mini"]}
    fetch_models.assert_awaited_once_with(
        api_base="https://api.example.com/v1",
        api_key="sk-test",
    )


def test_setup_apply_tests_candidate_and_writes_primary_model() -> None:
    client = _build_server(_StubChatService())
    current_config = {
        "LLM_MODELS": [
            {
                "id": "main",
                "label": "主模型",
                "enabled": True,
                "isPrimary": True,
                "model": "gpt-4o-mini",
                "apiBase": None,
                "apiKey": "",
                "extraHeaders": {},
                "maxTokens": 8192,
                "temperature": 0.7,
                "thinkingBudgetTokens": 0,
                "capabilities": {
                    "imageInput": True,
                    "audioInput": False,
                    "documentInput": True,
                    "toolCalling": True,
                    "streaming": True,
                },
            }
        ]
    }
    write_result = (True, SimpleNamespace(), ["LLM_MODELS"], [], [])
    test_model = AsyncMock(return_value=None)

    with patch("auraeve.webui.server.cfg.export_config", return_value=current_config), patch(
        "auraeve.webui.server.cfg.write",
        return_value=write_result,
    ) as write_mock, patch(
        "auraeve.webui.server.test_setup_model",
        test_model,
        create=True,
    ):
        response = client.post(
            "/api/webui/setup/apply",
            headers={"X-WEBUI-TOKEN": "secret"},
            json={
                "apiBase": "https://api.example.com/v1",
                "apiKey": "sk-test",
                "model": "gpt-4.1-mini",
            },
        )

    assert response.status_code == 200
    assert response.json()["configured"] is True
    test_model.assert_awaited_once()
    written_models = write_mock.call_args.args[0]["LLM_MODELS"]
    assert written_models[0]["model"] == "gpt-4.1-mini"
    assert written_models[0]["apiBase"] == "https://api.example.com/v1"
    assert written_models[0]["apiKey"] == "sk-test"


def test_setup_apply_refreshes_running_chat_runtime_model() -> None:
    chat = _RuntimeAwareStubChatService()
    client = _build_server(chat)
    current_config = {
        "LLM_MODELS": [
            {
                "id": "main",
                "label": "主模型",
                "enabled": True,
                "isPrimary": True,
                "model": "gpt-4o-mini",
                "apiBase": None,
                "apiKey": "",
                "extraHeaders": {},
                "maxTokens": 8192,
                "temperature": 0.7,
                "thinkingBudgetTokens": 0,
                "capabilities": {
                    "imageInput": True,
                    "audioInput": False,
                    "documentInput": True,
                    "toolCalling": True,
                    "streaming": True,
                },
            }
        ]
    }
    write_result = (True, SimpleNamespace(), ["LLM_MODELS"], [], [])

    with patch("auraeve.webui.server.cfg.export_config", return_value=current_config), patch(
        "auraeve.webui.server.cfg.write",
        return_value=write_result,
    ), patch(
        "auraeve.webui.server.test_setup_model",
        AsyncMock(return_value=None),
        create=True,
    ):
        response = client.post(
            "/api/webui/setup/apply",
            headers={"X-WEBUI-TOKEN": "secret"},
            json={
                "apiBase": "https://api.example.com/v1",
                "apiKey": "sk-test",
                "model": "gpt-4.1-mini",
            },
        )

    assert response.status_code == 200
    assert chat.applied_configs
    applied_models = chat.applied_configs[0]["LLM_MODELS"]
    assert applied_models[0]["model"] == "gpt-4.1-mini"
    assert applied_models[0]["apiKey"] == "sk-test"


def test_setup_model_uses_streaming_tool_compatible_probe() -> None:
    captured: dict = {}

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _FakeResponse()

    with patch("auraeve.webui.server.httpx.AsyncClient", _FakeClient):
        import asyncio

        asyncio.run(
            run_setup_model_probe(
                api_base="https://api.example.com/v1",
                api_key="sk-test",
                model="gpt-4o-mini",
            )
        )

    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["json"]["stream"] is True
    assert captured["json"]["tool_choice"] == "none"
    assert captured["json"]["tools"][0]["type"] == "function"
