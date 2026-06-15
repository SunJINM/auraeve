"""WebUI FastAPI service routes and lifecycle."""
from __future__ import annotations

import asyncio
import json
import contextlib
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, ConfigDict

import auraeve.config as cfg
from auraeve.webui.auth import verify_token
from auraeve.webui.chat_transcript_service import project_history_into_transcript_blocks
from auraeve.webui.chat_service import ChatService
from auraeve.webui.chat_console_service import ChatConsoleService
from auraeve.webui.schemas import (
    ChatAbortRequest,
    ChatAbortResponse,
    ChatConsoleSnapshotResponse,
    ChatHistoryResponse,
    ChatSessionCreateResponse,
    ChatSessionDeleteResponse,
    ChatSessionsResponse,
    ChatTranscriptHistoryResponse,
    ChatSendRequest,
    ChatSendResponse,
)


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
PLACEHOLDER_API_KEYS = {"YOUR_LLM_API_KEY", "your-api-key", "sk-..."}


class SetupStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configured: bool
    model: str
    apiBase: str


class SetupModelsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    apiBase: str = ""
    apiKey: str


class SetupModelsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: list[str]


class SetupApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    apiBase: str = ""
    apiKey: str
    model: str


def _normalize_api_base(api_base: str | None) -> str:
    raw = (api_base or "").strip().rstrip("/")
    return raw or DEFAULT_OPENAI_BASE_URL


def _is_configured_api_key(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    key = value.strip()
    return bool(key) and key not in PLACEHOLDER_API_KEYS


def _primary_model_config() -> dict[str, Any]:
    models = cfg.export_config(mask_sensitive=False).get("LLM_MODELS") or []
    if isinstance(models, list):
        for item in models:
            if isinstance(item, dict) and item.get("enabled", True) and item.get("isPrimary"):
                return dict(item)
        for item in models:
            if isinstance(item, dict) and item.get("enabled", True):
                return dict(item)
    return {}


def _setup_status_payload() -> SetupStatusResponse:
    primary = _primary_model_config()
    return SetupStatusResponse(
        configured=_is_configured_api_key(primary.get("apiKey")),
        model=str(primary.get("model") or ""),
        apiBase=str(primary.get("apiBase") or ""),
    )


async def fetch_setup_models(*, api_base: str, api_key: str) -> list[str]:
    if not _is_configured_api_key(api_key):
        raise HTTPException(status_code=400, detail="API Key 不能为空")
    url = f"{_normalize_api_base(api_base)}/models"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {api_key.strip()}"})
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=400, detail=f"模型列表拉取失败：HTTP {exc.response.status_code}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"模型列表拉取失败：{exc}") from exc

    raw_models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_models, list):
        return []
    names = sorted(
        {
            str(item.get("id")).strip()
            for item in raw_models
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
    )
    return names


async def test_setup_model(*, api_base: str, api_key: str, model: str) -> None:
    if not _is_configured_api_key(api_key):
        raise HTTPException(status_code=400, detail="API Key 不能为空")
    if not model.strip():
        raise HTTPException(status_code=400, detail="模型不能为空")
    url = f"{_normalize_api_base(api_base)}/chat/completions"
    body = {
        "model": model.strip(),
        "messages": [{"role": "user", "content": "只回复 ok，不要调用工具。"}],
        "max_tokens": 1,
        "stream": True,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "auraeve_setup_probe",
                    "description": "配置测试探针，不应被调用。",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            }
        ],
        "tool_choice": "none",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key.strip()}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=400, detail=f"模型测试失败：HTTP {exc.response.status_code}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"模型测试失败：{exc}") from exc


def _updated_primary_models(req: SetupApplyRequest) -> list[dict[str, Any]]:
    current = cfg.export_config(mask_sensitive=False).get("LLM_MODELS") or []
    models = [dict(item) for item in current if isinstance(item, dict)] if isinstance(current, list) else []
    if not models:
        models = [dict((cfg.DEFAULTS.get("LLM_MODELS") or [{}])[0])]

    primary_index = 0
    for idx, item in enumerate(models):
        if item.get("enabled", True) and item.get("isPrimary"):
            primary_index = idx
            break

    for idx, item in enumerate(models):
        item["isPrimary"] = idx == primary_index

    primary = dict(models[primary_index])
    primary.update(
        {
            "enabled": True,
            "isPrimary": True,
            "model": req.model.strip(),
            "apiBase": req.apiBase.strip() or None,
            "apiKey": req.apiKey.strip(),
        }
    )
    models[primary_index] = primary
    return models


class WebUIServer:
    """WebUI HTTP service, embeddable in the main asyncio loop."""

    def __init__(
        self,
        chat_service: ChatService,
        host: str = "0.0.0.0",
        port: int = 8080,
        token: str = "",
        static_dir: Path | None = None,
        subagent_executor: Any | None = None,
    ) -> None:
        self._chat = chat_service
        self._host = host
        self._port = port
        self._token = token
        self._static_dir = static_dir
        self._chat_console = ChatConsoleService(
            chat_service,
            getattr(subagent_executor, "_store", None),
            task_base_dir=cfg.resolve_state_dir() / "tasks",
        )
        self._server: uvicorn.Server | None = None
        self._stopped = asyncio.Event()
        self._app = self._build_app()

    async def start(self) -> None:
        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level="warning",
            access_log=False,
            timeout_graceful_shutdown=2,
        )
        self._stopped.clear()
        self._server = uvicorn.Server(config)
        logger.info(f"WebUI 服务监听：http://{self._host}:{self._port}")
        try:
            # AuraEve 统一管理进程信号；uvicorn.Server.serve() 会覆盖 Ctrl+C 处理器。
            await self._server._serve()  # noqa: SLF001
        finally:
            self._stopped.set()

    async def stop(self) -> None:
        close_chat = getattr(self._chat, "close", None)
        if callable(close_chat):
            await close_chat()
        if self._server:
            self._server.should_exit = True
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=3)

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="AuraEve WebUI", docs_url=None, redoc_url=None)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        auth = Depends(verify_token(self._token))

        @app.get("/api/webui/health")
        async def health() -> dict[str, bool]:
            return {"ok": True}

        @app.get("/api/webui/auth/check", dependencies=[auth])
        async def auth_check() -> dict[str, bool]:
            return {"ok": True}

        @app.get("/api/webui/setup/status", response_model=SetupStatusResponse, dependencies=[auth])
        async def setup_status() -> SetupStatusResponse:
            return _setup_status_payload()

        @app.post("/api/webui/setup/models", response_model=SetupModelsResponse, dependencies=[auth])
        async def setup_models(req: SetupModelsRequest) -> SetupModelsResponse:
            models = await fetch_setup_models(api_base=req.apiBase, api_key=req.apiKey)
            return SetupModelsResponse(models=models)

        @app.post("/api/webui/setup/apply", response_model=SetupStatusResponse, dependencies=[auth])
        async def setup_apply(req: SetupApplyRequest) -> SetupStatusResponse:
            await test_setup_model(api_base=req.apiBase, api_key=req.apiKey, model=req.model)
            updated_models = _updated_primary_models(req)
            ok, _snapshot, _changed, _restart, issues = cfg.write({"LLM_MODELS": updated_models})
            if not ok:
                message = "; ".join(f"{item.get('path')}: {item.get('message')}" for item in issues)
                raise HTTPException(status_code=400, detail=message or "配置写入失败")
            apply_runtime_config = getattr(self._chat, "apply_runtime_config", None)
            if callable(apply_runtime_config):
                reload_result = await apply_runtime_config({"LLM_MODELS": updated_models})
                reload_issues = reload_result.get("issues") or []
                if reload_issues:
                    message = "; ".join(
                        str(item.get("message") or item) if isinstance(item, dict) else str(item)
                        for item in reload_issues
                    )
                    raise HTTPException(status_code=500, detail=message or "运行时配置刷新失败")
            return SetupStatusResponse(
                configured=True,
                model=req.model.strip(),
                apiBase=req.apiBase.strip(),
            )

        @app.get("/api/webui/chat/history", response_model=ChatHistoryResponse, dependencies=[auth])
        async def chat_history(
            sessionKey: str = Query(min_length=1, max_length=200),
            limit: int = Query(default=200, ge=1, le=1000),
        ) -> ChatHistoryResponse:
            msgs = self._chat.get_history(sessionKey, limit)
            return ChatHistoryResponse(sessionKey=sessionKey, messages=msgs)

        @app.get("/api/webui/chat/sessions", response_model=ChatSessionsResponse, dependencies=[auth])
        async def chat_sessions() -> ChatSessionsResponse:
            return ChatSessionsResponse(sessions=self._chat.list_sessions())

        @app.post("/api/webui/chat/sessions", response_model=ChatSessionCreateResponse, dependencies=[auth])
        async def chat_session_create() -> ChatSessionCreateResponse:
            return ChatSessionCreateResponse(session=self._chat.create_session())

        @app.delete("/api/webui/chat/sessions/{session_key:path}", response_model=ChatSessionDeleteResponse, dependencies=[auth])
        async def chat_session_delete(session_key: str) -> ChatSessionDeleteResponse:
            return ChatSessionDeleteResponse(ok=self._chat.delete_session(session_key))

        @app.get("/api/webui/chat/transcript", response_model=ChatTranscriptHistoryResponse, dependencies=[auth])
        async def chat_transcript(
            sessionKey: str = Query(min_length=1, max_length=200),
            limit: int = Query(default=200, ge=1, le=1000),
        ) -> ChatTranscriptHistoryResponse:
            if hasattr(self._chat, "get_transcript_messages"):
                raw_messages = self._chat.get_transcript_messages(sessionKey, limit)  # type: ignore[attr-defined]
            else:
                raw_messages = self._chat.get_history(sessionKey, limit)
            blocks = project_history_into_transcript_blocks(raw_messages)
            run = self._chat.get_runtime_status(sessionKey)
            return ChatTranscriptHistoryResponse(sessionKey=sessionKey, run=run, blocks=blocks)

        @app.get("/api/webui/chat/runtime", response_model=ChatConsoleSnapshotResponse, dependencies=[auth])
        async def chat_runtime(
            sessionKey: str = Query(min_length=1, max_length=200),
            limit: int = Query(default=100, ge=1, le=500),
        ) -> ChatConsoleSnapshotResponse:
            return ChatConsoleSnapshotResponse(**self._chat_console.get_snapshot(sessionKey, limit=limit))

        @app.post("/api/webui/chat/send", response_model=ChatSendResponse, dependencies=[auth])
        async def chat_send(req: ChatSendRequest) -> ChatSendResponse:
            run_id, status = await self._chat.send(
                session_key=req.sessionKey,
                message=req.message,
                idempotency_key=req.idempotencyKey,
                user_id=req.userId,
                display_name=req.displayName,
            )
            return ChatSendResponse(runId=run_id, status=status)  # type: ignore[arg-type]

        @app.post("/api/webui/chat/abort", response_model=ChatAbortResponse, dependencies=[auth])
        async def chat_abort(req: ChatAbortRequest) -> ChatAbortResponse:
            ok, run_id, status = await self._chat.abort(req.sessionKey, req.runId)
            return ChatAbortResponse(ok=ok, runId=run_id, status=status)  # type: ignore[arg-type]

        # 两个路径共享同一处理逻辑：/chat/events 为兼容路径，/chat/transcript/events 为当前前端使用路径
        @app.get("/api/webui/chat/events", dependencies=[auth])
        @app.get("/api/webui/chat/transcript/events", dependencies=[auth])
        async def chat_events(
            sessionKey: str = Query(min_length=1, max_length=200),
        ) -> StreamingResponse:
            async def _stream():
                async for event in self._chat.subscribe(sessionKey):
                    data = json.dumps(event, ensure_ascii=False)
                    yield f"data: {data}\n\n"

            return StreamingResponse(
                _stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "Connection": "keep-alive",
                },
            )

        # 资源产物：<img> 标签无法携带鉴权头，依赖随机不可枚举的 id 提供访问。
        @app.get("/api/webui/resources/{resource_id}/content")
        async def resource_content(resource_id: str) -> FileResponse:
            from auraeve import resource_store

            path = resource_store.resolve_resource_path(resource_id)
            if path is None:
                raise HTTPException(status_code=404, detail="资源不存在")
            return FileResponse(str(path))

        @app.get("/api/webui/resources/{resource_id}/download")
        async def resource_download(resource_id: str) -> FileResponse:
            from auraeve import resource_store

            path = resource_store.resolve_resource_path(resource_id)
            if path is None:
                raise HTTPException(status_code=404, detail="资源不存在")
            return FileResponse(str(path), filename=path.name)

        if self._static_dir and self._static_dir.exists():
            app.mount("/", StaticFiles(directory=str(self._static_dir), html=True), name="static")

        return app
