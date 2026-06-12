"""WebUI FastAPI service routes and lifecycle."""
from __future__ import annotations

import asyncio
import json
import contextlib
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

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
    ChatTranscriptHistoryResponse,
    ChatSendRequest,
    ChatSendResponse,
)


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

        @app.get("/api/webui/chat/history", response_model=ChatHistoryResponse, dependencies=[auth])
        async def chat_history(
            sessionKey: str = Query(min_length=1, max_length=200),
            limit: int = Query(default=200, ge=1, le=1000),
        ) -> ChatHistoryResponse:
            msgs = self._chat.get_history(sessionKey, limit)
            return ChatHistoryResponse(sessionKey=sessionKey, messages=msgs)

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

        if self._static_dir and self._static_dir.exists():
            app.mount("/", StaticFiles(directory=str(self._static_dir), html=True), name="static")

        return app
