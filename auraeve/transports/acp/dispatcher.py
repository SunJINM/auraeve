"""ACP JSON-RPC 方法路由器。"""
from __future__ import annotations

import uuid
from typing import Any, TYPE_CHECKING

from loguru import logger

from auraeve.bus.events import InboundMessage
from auraeve.domain.sessions.models import SessionRecord
from auraeve.transports.acp.protocol import (
    JsonRpcRequest, JsonRpcResponse, JsonRpcError, JsonRpcNotification,
    InitializeResult, AcpCapabilities,
    NewSessionParams, NewSessionResult,
    LoadSessionResult,
    PromptResult,
    ListSessionsResult, SessionInfo,
)

if TYPE_CHECKING:
    from auraeve.bus.queue import MessageBus
    from auraeve.services.session_service import SessionService

# ACP 自定义错误码
ERR_SESSION_NOT_FOUND = -32001
ERR_SESSION_ALREADY_EXISTS = -32002
ERR_PROMPT_TOO_LARGE = -32003


def _extract_text_from_blocks(blocks: list[dict[str, Any]]) -> str:
    parts = []
    for block in blocks:
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


class ACPDispatcher:
    """无状态 JSON-RPC 方法路由器。每次调用都完整传入所需依赖。"""

    def __init__(
        self,
        bus: "MessageBus",
        session_service: "SessionService",
        agent_id: str = "main",
        workspace_id: str = "default",
    ) -> None:
        self._bus = bus
        self._session_service = session_service
        self._agent_id = agent_id
        self._workspace_id = workspace_id
        # 活跃 cancel 信号：run_id -> asyncio.Event
        self._cancel_signals: dict[str, Any] = {}

    async def dispatch(
        self,
        msg: JsonRpcRequest | JsonRpcNotification | JsonRpcError,
    ) -> JsonRpcResponse | JsonRpcError | None:
        if isinstance(msg, JsonRpcError):
            return msg

        if isinstance(msg, JsonRpcNotification):
            return await self._handle_notification(msg)

        # JsonRpcRequest
        method = msg.method
        try:
            if method == "initialize":
                return await self._handle_initialize(msg)
            if method == "newSession":
                return await self._handle_new_session(msg)
            if method == "loadSession":
                return await self._handle_load_session(msg)
            if method == "prompt":
                return await self._handle_prompt(msg)
            if method == "unstable_listSessions":
                return await self._handle_list_sessions(msg)
            if method == "setSessionMode":
                return await self._handle_set_session_mode(msg)
            if method == "setSessionConfigOption":
                return await self._handle_set_session_config_option(msg)
            return JsonRpcError(id=msg.id, code=-32601, message=f"Method not found: {method}")
        except Exception as exc:
            logger.exception(f"[acp] dispatch error for method={method}: {exc}")
            return JsonRpcError(id=msg.id, code=-32603, message=f"Internal error: {exc}")

    async def _handle_notification(self, notif: JsonRpcNotification) -> None:
        if notif.method == "cancel":
            run_id = notif.params.get("runId", "")
            if run_id in self._cancel_signals:
                self._cancel_signals[run_id].set()
            logger.info(f"[acp] cancel signal for runId={run_id}")
        return None

    async def _handle_initialize(self, req: JsonRpcRequest) -> JsonRpcResponse:
        result = InitializeResult(
            protocolVersion="1.0",
            agentId=self._agent_id,
            capabilities=AcpCapabilities(),
        )
        return JsonRpcResponse(id=req.id, result=result.to_dict())

    async def _handle_new_session(self, req: JsonRpcRequest) -> JsonRpcResponse:
        agent_id = req.params.get("agentId", self._agent_id)
        cwd = req.params.get("cwd")
        mode = req.params.get("mode", "persistent")
        thread_id = uuid.uuid4().hex[:12]
        session = SessionRecord(
            session_id=f"acp-{uuid.uuid4().hex[:16]}",
            session_key=f"dev:{agent_id}:{self._workspace_id}:{thread_id}",
            session_type="dev_acp",
            runtime_type="acp",
            agent_id=agent_id,
            workspace_id=self._workspace_id,
            thread_id=thread_id,
            state="idle",
            metadata={"cwd": cwd or "", "mode": mode},
        )
        self._session_service.create_session(session)
        info = SessionInfo(sessionId=session.session_id, sessionKey=session.session_key, state=session.state)
        return JsonRpcResponse(id=req.id, result=NewSessionResult(session=info).to_dict())

    async def _handle_load_session(self, req: JsonRpcRequest) -> JsonRpcResponse | JsonRpcError:
        session_id = req.params.get("sessionId", "")
        session = self._session_service.get_session(session_id)
        if session is None:
            return JsonRpcError(id=req.id, code=ERR_SESSION_NOT_FOUND, message=f"Session not found: {session_id}")
        info = SessionInfo(sessionId=session.session_id, sessionKey=session.session_key, state=session.state)
        return JsonRpcResponse(id=req.id, result=LoadSessionResult(session=info, loaded=True).to_dict())

    async def _handle_prompt(self, req: JsonRpcRequest) -> JsonRpcResponse | JsonRpcError:
        session_id = req.params.get("sessionId", "")
        run_id = req.params.get("runId", uuid.uuid4().hex)
        blocks = req.params.get("blocks", [])
        metadata = req.params.get("metadata", {})

        session = self._session_service.get_session(session_id)
        if session is None:
            return JsonRpcError(id=req.id, code=ERR_SESSION_NOT_FOUND, message=f"Session not found: {session_id}")

        text = _extract_text_from_blocks(blocks)
        inbound = InboundMessage(
            channel=f"acp:{session_id}",
            sender_id=session.agent_id,
            chat_id=session_id,
            content=text,
            metadata={
                "session_type": "dev_acp",
                "run_id": run_id,
                "session_key": session.session_key,
                "acp_blocks": blocks,
                **metadata,
            },
        )
        await self._bus.publish_inbound(inbound)
        return JsonRpcResponse(id=req.id, result=PromptResult(runId=run_id, stopReason="stop").to_dict())

    async def _handle_list_sessions(self, req: JsonRpcRequest) -> JsonRpcResponse:
        all_sessions = self._session_service.list_sessions()
        dev_sessions = [s for s in all_sessions if s.session_type == "dev_acp"]
        infos = [SessionInfo(sessionId=s.session_id, sessionKey=s.session_key, state=s.state) for s in dev_sessions]
        return JsonRpcResponse(id=req.id, result=ListSessionsResult(sessions=infos, total=len(infos)).to_dict())

    async def _handle_set_session_mode(self, req: JsonRpcRequest) -> JsonRpcResponse | JsonRpcError:
        session_id = req.params.get("sessionId", "")
        session = self._session_service.get_session(session_id)
        if session is None:
            return JsonRpcError(id=req.id, code=ERR_SESSION_NOT_FOUND, message=f"Session not found: {session_id}")
        session.metadata["thought_level"] = req.params.get("mode", "adaptive")
        self._session_service.update_session(session)
        return JsonRpcResponse(id=req.id, result={"ok": True})

    async def _handle_set_session_config_option(self, req: JsonRpcRequest) -> JsonRpcResponse | JsonRpcError:
        session_id = req.params.get("sessionId", "")
        session = self._session_service.get_session(session_id)
        if session is None:
            return JsonRpcError(id=req.id, code=ERR_SESSION_NOT_FOUND, message=f"Session not found: {session_id}")
        key = req.params.get("key", "")
        value = req.params.get("value", "")
        session.metadata[key] = value
        self._session_service.update_session(session)
        return JsonRpcResponse(id=req.id, result={"ok": True})
