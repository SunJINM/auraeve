"""WebUI FastAPI service routes and lifecycle."""
from __future__ import annotations

import asyncio
import json
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
from auraeve.webui.chat_service import ChatService
from auraeve.webui.config_service import ConfigService
from auraeve.webui.mcp_service import MCPWebService
from auraeve.webui.node_service import NodeWebService
from auraeve.webui.plugin_service import PluginWebService
from auraeve.webui.log_service import LogWebService
from auraeve.webui.skill_service import SkillWebService
from auraeve.webui.upload_service import UploadWebService
from auraeve.webui.profile_service import ProfileWebService
from auraeve.webui.dev_session_service import DevSessionService
from auraeve.webui.schemas import (
    ChatAbortRequest,
    ChatAbortResponse,
    ChatHistoryResponse,
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
    PluginActionResponse,
    PluginEnableRequest,
    PluginInfoResponse,
    PluginInstallRequest,
    PluginListResponse,
    PluginUninstallRequest,
    SkillActionResponse,
    SkillEnableRequest,
    SkillHubInstallRequest,
    SkillInfoResponse,
    SkillInstallRequest,
    SkillListResponse,
    SkillUploadInstallRequest,
    SkillUploadResponse,
    SkillSyncRequest,
    LogsTailResponse,
    LogsSearchRequest,
    LogsSearchResponse,
    LogsStatsResponse,
    LogsContextResponse,
    LogsExportRequest,
    ProfileImportResponse,
    RestartResponse,
    DevSessionListResponse,
    NodeListResponse,
    NodeDetailResponse,
    NodeActionResponse,
    TaskListResponse,
    TaskDetailResponse,
    TaskActionRequest,
    TaskSteerRequest,
    TaskSubmitRequest,
    ApprovalListResponse,
    ApprovalDecideRequest,
    DeltaListResponse,
    NodeOverviewResponse,
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
        dev_session_service: DevSessionService | None = None,
        orchestrator: Any | None = None,
    ) -> None:
        self._chat = chat_service
        self._config = config_service
        self._host = host
        self._port = port
        self._token = token
        self._static_dir = static_dir
        resolved_workspace = workspace or cfg.resolve_workspace_dir("default")
        self._plugins = PluginWebService(resolved_workspace)
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
        self._nodes = NodeWebService(orchestrator) if orchestrator else None
        self._server: uvicorn.Server | None = None
        self._restart_callback = restart_callback
        self._dev_sessions = dev_session_service
        self._upload = UploadWebService()
        self._profile = ProfileWebService()
        self._logs = LogWebService()
        self._app = self._build_app()

    async def start(self) -> None:
        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        logger.info(f"WebUI started: http://{self._host}:{self._port}")
        await self._server.serve()

    async def stop(self) -> None:
        if self._server:
            self._server.should_exit = True

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
            try:
                msgs = self._chat.get_history(sessionKey, limit)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            return ChatHistoryResponse(sessionKey=sessionKey, messages=msgs)

        @app.post("/api/webui/chat/send", response_model=ChatSendResponse, dependencies=[auth])
        async def chat_send(req: ChatSendRequest) -> ChatSendResponse:
            try:
                run_id, status = await self._chat.send(
                    session_key=req.sessionKey,
                    message=req.message,
                    idempotency_key=req.idempotencyKey,
                    user_id=req.userId,
                    display_name=req.displayName,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            return ChatSendResponse(runId=run_id, status=status)  # type: ignore[arg-type]

        @app.post("/api/webui/chat/abort", response_model=ChatAbortResponse, dependencies=[auth])
        async def chat_abort(req: ChatAbortRequest) -> ChatAbortResponse:
            try:
                ok, run_id, status = await self._chat.abort(req.sessionKey, req.runId)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            return ChatAbortResponse(ok=ok, runId=run_id, status=status)  # type: ignore[arg-type]

        @app.get("/api/webui/dev/sessions", response_model=DevSessionListResponse, dependencies=[auth])
        async def dev_sessions_list(
            limit: int = Query(default=200, ge=1, le=1000),
        ) -> DevSessionListResponse:
            if self._dev_sessions is None:
                raise HTTPException(
                    status_code=503,
                    detail="dev session api is disabled until dev_session_service is injected",
                )
            sessions = self._dev_sessions.list_sessions(limit=None)
            return DevSessionListResponse(
                ok=True,
                sessions=[self._dev_sessions.to_dict(session) for session in sessions[:limit]],
                total=len(sessions),
            )

        @app.get("/api/webui/chat/events", dependencies=[auth])
        async def chat_events(
            sessionKey: str = Query(min_length=1, max_length=200),
        ) -> StreamingResponse:
            try:
                self._chat._ensure_legacy_chat_session(sessionKey)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

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

        @app.get("/api/webui/logs/stream", dependencies=[auth])
        async def logs_stream(
            levels: str = Query(default=""),
            subsystems: str = Query(default=""),
            text: str = Query(default="", max_length=500),
        ) -> StreamingResponse:
            level_list = [item.strip() for item in levels.split(",") if item.strip()]
            subsystem_list = [item.strip() for item in subsystems.split(",") if item.strip()]

            async def _stream():
                async for item in self._logs.subscribe(
                    levels=level_list,
                    subsystems=subsystem_list,
                    text=text,
                ):
                    data = json.dumps(item, ensure_ascii=False)
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

        @app.get("/api/webui/logs/tail", response_model=LogsTailResponse, dependencies=[auth])
        async def logs_tail(
            cursor: int | None = Query(default=None, ge=0),
            limit: int = Query(default=500, ge=1, le=5000),
            maxBytes: int = Query(default=250000, ge=1, le=1000000),
        ) -> LogsTailResponse:
            return LogsTailResponse(**self._logs.tail(cursor=cursor, limit=limit, max_bytes=maxBytes))

        @app.post("/api/webui/logs/search", response_model=LogsSearchResponse, dependencies=[auth])
        async def logs_search(req: LogsSearchRequest) -> LogsSearchResponse:
            result = self._logs.search(
                levels=req.levels,
                subsystems=req.subsystems,
                kinds=req.kinds,
                text=req.text,
                session_key=req.sessionKey,
                run_id=req.runId,
                channel=req.channel,
                ts_from=req.fromTs,
                ts_to=req.toTs,
                limit=req.limit,
                offset=req.offset,
            )
            return LogsSearchResponse(**result)

        @app.get("/api/webui/logs/stats", response_model=LogsStatsResponse, dependencies=[auth])
        async def logs_stats(
            fromTs: str | None = Query(default=None),
            toTs: str | None = Query(default=None),
        ) -> LogsStatsResponse:
            return LogsStatsResponse(**self._logs.stats(ts_from=fromTs, ts_to=toTs))

        @app.get("/api/webui/logs/context", response_model=LogsContextResponse, dependencies=[auth])
        async def logs_context(
            eventId: str = Query(min_length=1, max_length=80),
            before: int = Query(default=20, ge=0, le=200),
            after: int = Query(default=20, ge=0, le=200),
        ) -> LogsContextResponse:
            return LogsContextResponse(**self._logs.context(event_id=eventId, before=before, after=after))

        @app.post("/api/webui/logs/export", dependencies=[auth])
        async def logs_export(req: LogsExportRequest):
            content, media_type, filename = self._logs.export(
                export_format=req.format,
                levels=req.levels,
                subsystems=req.subsystems,
                kinds=req.kinds,
                text=req.text,
                session_key=req.sessionKey,
                run_id=req.runId,
                channel=req.channel,
                ts_from=req.fromTs,
                ts_to=req.toTs,
                limit=req.limit,
            )
            return StreamingResponse(
                iter([content.encode("utf-8")]),
                media_type=media_type,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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

        @app.get("/api/webui/plugins/list", response_model=PluginListResponse, dependencies=[auth])
        async def plugins_list() -> PluginListResponse:
            return PluginListResponse(**self._plugins.list())

        @app.get("/api/webui/plugins/info", response_model=PluginInfoResponse, dependencies=[auth])
        async def plugins_info(id: str = Query(min_length=1, max_length=200)) -> PluginInfoResponse:
            return PluginInfoResponse(**self._plugins.info(id))

        @app.post("/api/webui/plugins/install", response_model=PluginActionResponse, dependencies=[auth])
        async def plugins_install(req: PluginInstallRequest) -> PluginActionResponse:
            return PluginActionResponse(**self._plugins.install(req.path, req.link))

        @app.post("/api/webui/plugins/uninstall", response_model=PluginActionResponse, dependencies=[auth])
        async def plugins_uninstall(req: PluginUninstallRequest) -> PluginActionResponse:
            return PluginActionResponse(**self._plugins.uninstall(req.id, req.keepFiles))

        @app.post("/api/webui/plugins/enable", response_model=PluginActionResponse, dependencies=[auth])
        async def plugins_enable(req: PluginEnableRequest) -> PluginActionResponse:
            return PluginActionResponse(**self._plugins.enable(req.id))

        @app.post("/api/webui/plugins/disable", response_model=PluginActionResponse, dependencies=[auth])
        async def plugins_disable(req: PluginEnableRequest) -> PluginActionResponse:
            return PluginActionResponse(**self._plugins.disable(req.id))

        @app.get("/api/webui/plugins/doctor", response_model=dict[str, Any], dependencies=[auth])
        async def plugins_doctor() -> dict[str, Any]:
            return self._plugins.doctor()

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
                logger.info("WebUI 收到重启请求，即将重启服务...")
                asyncio.get_running_loop().call_later(0.5, lambda: asyncio.create_task(self._restart_callback()))  # type: ignore[misc]
                return RestartResponse(ok=True, message="服务即将重启，请稍候...")

        # ── 节点控制模块路由 ──────────────────────────────────────────────
        if self._nodes is not None:
            @app.get("/api/webui/nodes/overview", response_model=NodeOverviewResponse, dependencies=[auth])
            async def nodes_overview() -> NodeOverviewResponse:
                return NodeOverviewResponse(**self._nodes.get_overview())

            @app.get("/api/webui/nodes/list", response_model=NodeListResponse, dependencies=[auth])
            async def nodes_list() -> NodeListResponse:
                return NodeListResponse(**self._nodes.list_nodes())

            @app.get("/api/webui/nodes/detail", response_model=NodeDetailResponse, dependencies=[auth])
            async def nodes_detail(nodeId: str = Query(min_length=1, max_length=100)) -> NodeDetailResponse:
                return NodeDetailResponse(**self._nodes.get_node_detail(nodeId))

            @app.post("/api/webui/nodes/disconnect", response_model=NodeActionResponse, dependencies=[auth])
            async def nodes_disconnect(req: TaskActionRequest) -> NodeActionResponse:
                return NodeActionResponse(**self._nodes.disconnect_node(req.taskId))

            @app.get("/api/webui/nodes/tasks", response_model=TaskListResponse, dependencies=[auth])
            async def nodes_tasks(
                status: str | None = Query(default=None, max_length=30),
                nodeId: str | None = Query(default=None, max_length=100),
                limit: int = Query(default=50, ge=1, le=500),
            ) -> TaskListResponse:
                return TaskListResponse(**self._nodes.list_tasks(status=status, node_id=nodeId, limit=limit))

            @app.get("/api/webui/nodes/tasks/detail", response_model=TaskDetailResponse, dependencies=[auth])
            async def nodes_task_detail(taskId: str = Query(min_length=1, max_length=100)) -> TaskDetailResponse:
                return TaskDetailResponse(**self._nodes.get_task_detail(taskId))

            @app.post("/api/webui/nodes/tasks/pause", response_model=NodeActionResponse, dependencies=[auth])
            async def nodes_task_pause(req: TaskActionRequest) -> NodeActionResponse:
                return NodeActionResponse(**(await self._nodes.pause_task(req.taskId)))

            @app.post("/api/webui/nodes/tasks/resume", response_model=NodeActionResponse, dependencies=[auth])
            async def nodes_task_resume(req: TaskActionRequest) -> NodeActionResponse:
                return NodeActionResponse(**(await self._nodes.resume_task(req.taskId)))

            @app.post("/api/webui/nodes/tasks/cancel", response_model=NodeActionResponse, dependencies=[auth])
            async def nodes_task_cancel(req: TaskActionRequest) -> NodeActionResponse:
                return NodeActionResponse(**(await self._nodes.cancel_task(req.taskId, req.reason or "webui_cancel")))

            @app.post("/api/webui/nodes/tasks/steer", response_model=NodeActionResponse, dependencies=[auth])
            async def nodes_task_steer(req: TaskSteerRequest) -> NodeActionResponse:
                return NodeActionResponse(**(await self._nodes.steer_task(req.taskId, req.message)))

            @app.post("/api/webui/nodes/tasks/submit", response_model=NodeActionResponse, dependencies=[auth])
            async def nodes_task_submit(req: TaskSubmitRequest) -> NodeActionResponse:
                return NodeActionResponse(**(await self._nodes.submit_task(
                    goal=req.goal,
                    priority=req.priority,
                    assigned_node_id=req.assignedNodeId,
                    origin_channel=req.originChannel,
                    origin_chat_id=req.originChatId,
                )))

            @app.get("/api/webui/nodes/approvals", response_model=ApprovalListResponse, dependencies=[auth])
            async def nodes_approvals(
                status: str | None = Query(default=None, max_length=30),
                limit: int = Query(default=100, ge=1, le=500),
            ) -> ApprovalListResponse:
                return ApprovalListResponse(**self._nodes.list_approvals(status=status, limit=limit))

            @app.post("/api/webui/nodes/approvals/decide", response_model=NodeActionResponse, dependencies=[auth])
            async def nodes_approval_decide(req: ApprovalDecideRequest) -> NodeActionResponse:
                return NodeActionResponse(**self._nodes.decide_approval(req.approvalId, req.decision, req.decidedBy))

            @app.get("/api/webui/nodes/deltas", response_model=DeltaListResponse, dependencies=[auth])
            async def nodes_deltas(
                mergeStatus: str | None = Query(default=None, max_length=30),
                nodeId: str | None = Query(default=None, max_length=100),
                limit: int = Query(default=100, ge=1, le=500),
            ) -> DeltaListResponse:
                return DeltaListResponse(**self._nodes.list_deltas(
                    merge_status=mergeStatus, node_id=nodeId, limit=limit,
                ))

            @app.post("/api/webui/nodes/memory/merge", response_model=NodeActionResponse, dependencies=[auth])
            async def nodes_memory_merge() -> NodeActionResponse:
                return NodeActionResponse(**self._nodes.trigger_merge())

            @app.get("/api/webui/nodes/stream", dependencies=[auth])
            async def nodes_stream() -> StreamingResponse:
                async def _stream():
                    async for event in self._nodes.subscribe():
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
