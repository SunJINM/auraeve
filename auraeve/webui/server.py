"""WebUI FastAPI service routes and lifecycle."""
from __future__ import annotations

import asyncio
import json
import contextlib
from pathlib import Path
from typing import Any, Awaitable, Callable

import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

import auraeve.config as cfg
from auraeve.webui.auth import verify_token
from auraeve.webui.chat_transcript_service import project_history_into_transcript_blocks
from auraeve.webui.chat_service import ChatService
from auraeve.webui.chat_console_service import ChatConsoleService
from auraeve.webui.config_service import ConfigService
from auraeve.webui.mcp_service import MCPWebService
from auraeve.webui.skill_service import SkillWebService
from auraeve.webui.upload_service import UploadWebService
from auraeve.webui.profile_service import ProfileWebService
from auraeve.webui.schemas import (
    ChatAbortRequest,
    ChatAbortResponse,
    ChatConsoleSnapshotResponse,
    ChatHistoryResponse,
    ChatTranscriptHistoryResponse,
    ChatSendRequest,
    ChatSendResponse,
    ConfigGetResponse,
    ConfigSchemaResponse,
    ConfigWriteRequest,
    ConfigWriteResponse,
    MCPApplyResponse,
    MCPAuditResponse,
    MCPConfigRequest,
    MCPConfigResponse,
    MCPEventsResponse,
    MCPMetricsResponse,
    MCPReconnectAllResponse,
    MCPReconnectRequest,
    MCPStatusResponse,
    MCPTemplatesResponse,
    MCPTestRequest,
    MCPTestResponse,
    MCPValidateRequest,
    MCPValidateResponse,
    SkillActionResponse,
    SkillEnableRequest,
    SkillHubInstallRequest,
    SkillInfoResponse,
    SkillInstallRequest,
    SkillListResponse,
    SkillUploadInstallRequest,
    SkillUploadResponse,
    SkillSyncRequest,
    ProfileImportResponse,
    RestartResponse,
)


class WebUIServer:
    """WebUI HTTP service, embeddable in the main asyncio loop."""

    def __init__(
        self,
        chat_service: ChatService,
        config_service: ConfigService,
        host: str = "0.0.0.0",
        port: int = 8080,
        token: str = "",
        static_dir: Path | None = None,
        workspace: Path | None = None,
        mcp_status_provider: Callable[[], dict[str, Any]] | None = None,
        mcp_events_provider: Callable[[], list[dict[str, Any]]] | None = None,
        mcp_reconnect_provider: Callable[[str], Awaitable[dict[str, Any]]] | None = None,
        restart_callback: Callable[[], Awaitable[None]] | None = None,
        subagent_executor: Any | None = None,
    ) -> None:
        self._chat = chat_service
        self._config = config_service
        self._host = host
        self._port = port
        self._token = token
        self._static_dir = static_dir
        resolved_workspace = workspace or cfg.resolve_workspace_dir("default")
        self._skills = SkillWebService(resolved_workspace)
        self._mcp = (
            MCPWebService(
                config_service,
                get_status=mcp_status_provider,
                get_events=mcp_events_provider,
                reconnect_server=mcp_reconnect_provider,
            )
            if mcp_status_provider and mcp_events_provider and mcp_reconnect_provider
            else None
        )
        self._chat_console = ChatConsoleService(
            chat_service,
            getattr(subagent_executor, "_store", None),
            task_base_dir=cfg.resolve_state_dir() / "tasks",
        )
        self._server: uvicorn.Server | None = None
        self._stopped = asyncio.Event()
        self._restart_callback = restart_callback
        self._upload = UploadWebService()
        self._profile = ProfileWebService()
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

        @app.get("/api/webui/chat/events", dependencies=[auth])
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

        @app.get("/api/webui/chat/transcript/events", dependencies=[auth])
        async def chat_transcript_events(
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

        @app.get("/api/webui/profile/export", dependencies=[auth])
        async def profile_export():
            content, filename = self._profile.export_archive()
            return StreamingResponse(
                iter([content]),
                media_type="application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        @app.post("/api/webui/profile/import", response_model=ProfileImportResponse, dependencies=[auth])
        async def profile_import(
            file: UploadFile = File(...),
            force: bool = Query(default=False),
        ) -> ProfileImportResponse:
            try:
                payload = await self._profile.import_archive(file, force=force)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc))
            except RuntimeError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"profile import failed: {exc}")
            return ProfileImportResponse(**payload)

        @app.get("/api/webui/config/get", response_model=ConfigGetResponse, dependencies=[auth])
        async def config_get() -> ConfigGetResponse:
            return self._config.get()

        @app.get("/api/webui/config/schema", response_model=ConfigSchemaResponse, dependencies=[auth])
        async def config_schema() -> ConfigSchemaResponse:
            return self._config.schema()

        @app.post("/api/webui/config/set", response_model=ConfigWriteResponse, dependencies=[auth])
        async def config_set(req: ConfigWriteRequest) -> ConfigWriteResponse:
            if not req.config:
                raise HTTPException(status_code=400, detail="config 字段不能为空")
            return self._config.set(req.baseHash, req.config)

        @app.post("/api/webui/config/apply", response_model=ConfigWriteResponse, dependencies=[auth])
        async def config_apply(req: ConfigWriteRequest) -> ConfigWriteResponse:
            if not req.config:
                raise HTTPException(status_code=400, detail="config 字段不能为空")
            return await self._config.apply(req.baseHash, req.config)

        if self._mcp is not None:
            @app.get("/api/webui/mcp/config", response_model=MCPConfigResponse, dependencies=[auth])
            async def mcp_config_get() -> MCPConfigResponse:
                return MCPConfigResponse(**self._mcp.get_config())

            @app.post("/api/webui/mcp/validate", response_model=MCPValidateResponse, dependencies=[auth])
            async def mcp_validate(req: MCPValidateRequest) -> MCPValidateResponse:
                return MCPValidateResponse(**self._mcp.validate(req.config))

            @app.post("/api/webui/mcp/set", response_model=MCPApplyResponse, dependencies=[auth])
            async def mcp_set(req: MCPConfigRequest) -> MCPApplyResponse:
                return MCPApplyResponse(**self._mcp.set_config(req.baseHash, req.config))

            @app.post("/api/webui/mcp/apply", response_model=MCPApplyResponse, dependencies=[auth])
            async def mcp_apply(req: MCPConfigRequest) -> MCPApplyResponse:
                return MCPApplyResponse(**(await self._mcp.apply_config(req.baseHash, req.config)))

            @app.get("/api/webui/mcp/status", response_model=MCPStatusResponse, dependencies=[auth])
            async def mcp_status() -> MCPStatusResponse:
                return MCPStatusResponse(**self._mcp.status())

            @app.get("/api/webui/mcp/events", response_model=MCPEventsResponse, dependencies=[auth])
            async def mcp_events() -> MCPEventsResponse:
                return MCPEventsResponse(**self._mcp.events())

            @app.post("/api/webui/mcp/reconnect", response_model=MCPStatusResponse, dependencies=[auth])
            async def mcp_reconnect(req: MCPReconnectRequest) -> MCPStatusResponse:
                return MCPStatusResponse(**(await self._mcp.reconnect(req.serverId)))

            @app.post("/api/webui/mcp/reconnect-all", response_model=MCPReconnectAllResponse, dependencies=[auth])
            async def mcp_reconnect_all() -> MCPReconnectAllResponse:
                return MCPReconnectAllResponse(**(await self._mcp.reconnect_all()))

            @app.get("/api/webui/mcp/templates", response_model=MCPTemplatesResponse, dependencies=[auth])
            async def mcp_templates() -> MCPTemplatesResponse:
                return MCPTemplatesResponse(**self._mcp.templates())

            @app.post("/api/webui/mcp/test", response_model=MCPTestResponse, dependencies=[auth])
            async def mcp_test(req: MCPTestRequest) -> MCPTestResponse:
                return MCPTestResponse(**(await self._mcp.test_connection(req.serverId, req.server)))

            @app.get("/api/webui/mcp/metrics", response_model=MCPMetricsResponse, dependencies=[auth])
            async def mcp_metrics() -> MCPMetricsResponse:
                return MCPMetricsResponse(**self._mcp.metrics())

            @app.get("/api/webui/mcp/audit", response_model=MCPAuditResponse, dependencies=[auth])
            async def mcp_audit(limit: int = Query(default=100, ge=1, le=500)) -> MCPAuditResponse:
                return MCPAuditResponse(**self._mcp.audit(limit))

        @app.get("/api/webui/skills/list", response_model=SkillListResponse, dependencies=[auth])
        async def skills_list() -> SkillListResponse:
            return SkillListResponse(**self._skills.list())

        @app.get("/api/webui/skills/info", response_model=SkillInfoResponse, dependencies=[auth])
        async def skills_info(id: str = Query(min_length=1, max_length=200)) -> SkillInfoResponse:
            return SkillInfoResponse(**self._skills.info(id))

        @app.get("/api/webui/skills/status", response_model=dict[str, Any], dependencies=[auth])
        async def skills_status() -> dict[str, Any]:
            return self._skills.status()

        @app.post("/api/webui/skills/install", response_model=SkillActionResponse, dependencies=[auth])
        async def skills_install(req: SkillInstallRequest) -> SkillActionResponse:
            return SkillActionResponse(**self._skills.install(req.id, req.installId))

        @app.post("/api/webui/skills/install-hub", response_model=SkillActionResponse, dependencies=[auth])
        async def skills_install_hub(req: SkillHubInstallRequest) -> SkillActionResponse:
            return SkillActionResponse(**self._skills.install_from_hub(req.slug, req.version, req.force))

        @app.post("/api/webui/skills/upload", response_model=SkillUploadResponse, dependencies=[auth])
        async def skills_upload(file: UploadFile = File(...)) -> SkillUploadResponse:
            return SkillUploadResponse(**(await self._upload.upload_skill_archive(file)))

        @app.post("/api/webui/skills/install-upload", response_model=SkillActionResponse, dependencies=[auth])
        async def skills_install_upload(req: SkillUploadInstallRequest) -> SkillActionResponse:
            return SkillActionResponse(**self._skills.install_from_upload(req.uploadId, req.force))

        @app.post("/api/webui/skills/enable", response_model=SkillActionResponse, dependencies=[auth])
        async def skills_enable(req: SkillEnableRequest) -> SkillActionResponse:
            return SkillActionResponse(**self._skills.enable(req.id))

        @app.post("/api/webui/skills/disable", response_model=SkillActionResponse, dependencies=[auth])
        async def skills_disable(req: SkillEnableRequest) -> SkillActionResponse:
            return SkillActionResponse(**self._skills.disable(req.id))

        @app.get("/api/webui/skills/doctor", response_model=dict[str, Any], dependencies=[auth])
        async def skills_doctor() -> dict[str, Any]:
            return self._skills.doctor()

        @app.post("/api/webui/skills/sync", response_model=SkillActionResponse, dependencies=[auth])
        async def skills_sync(req: SkillSyncRequest) -> SkillActionResponse:
            return SkillActionResponse(**self._skills.sync(all_skills=req.all, dry_run=req.dryRun))

        if self._restart_callback is not None:
            @app.post("/api/webui/restart", response_model=RestartResponse, dependencies=[auth])
            async def restart_service() -> RestartResponse:
                logger.info("WebUI 收到重启请求，准备重启 AuraEve")
                asyncio.get_running_loop().call_later(0.5, lambda: asyncio.create_task(self._restart_callback()))  # type: ignore[misc]
                return RestartResponse(ok=True, message="服务即将重启，请稍候...")

        if self._static_dir and self._static_dir.exists():
            app.mount("/", StaticFiles(directory=str(self._static_dir), html=True), name="static")

        return app
