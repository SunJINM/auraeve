"""WebUI 聊天服务：管理聊天会话、历史、发送、终止与 SSE 事件分发。"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from loguru import logger

from auraeve.bus.events import OutboundMessage
from auraeve.session.manager import SessionManager


@dataclass
class RunState:
    run_id: str
    session_key: str
    idempotency_key: str
    done: bool = False
    aborted: bool = False


class ChatService:
    """
    聊天业务层。

    职责：
    - 历史加载（复用 SessionManager）
    - 发送消息（publish_inbound 交给 RuntimeKernel 处理）
    - 终止（软中止：标记 done/aborted）
    - SSE 事件队列管理（每个 sessionKey 对应一个广播队列）
    """

    def __init__(self, session_manager: SessionManager, bus: Any) -> None:
        self._sm = session_manager
        self._bus = bus
        # run_id -> RunState
        self._runs: dict[str, RunState] = {}
        # idempotency_key -> run_id （防重入）
        self._idem: dict[str, str] = {}
        # session_key -> list[asyncio.Queue]（SSE 订阅者）
        self._sse_queues: dict[str, list[asyncio.Queue]] = {}

    # ─── 历史 ──────────────────────────────────────────────────────

    def get_history(self, session_key: str, limit: int = 200) -> list[dict]:
        session = self._sm.get_or_create(session_key)
        msgs = session.messages[-limit:] if limit else session.messages
        return [
            {
                "role": m.get("role", ""),
                "content": m.get("content", ""),
                "timestamp": m.get("timestamp", ""),
            }
            for m in msgs
        ]

    # ─── 发送 ──────────────────────────────────────────────────────

    async def send(
        self,
        session_key: str,
        message: str,
        idempotency_key: str,
        user_id: str,
        display_name: str | None = None,
    ) -> tuple[str, str]:
        """
        发布入站消息，返回 (run_id, status)。
        status = "in_flight" 表示幂等重入（相同 idempotencyKey 的请求）。
        """
        if idempotency_key in self._idem:
            run_id = self._idem[idempotency_key]
            return run_id, "in_flight"

        run_id = str(uuid.uuid4())
        state = RunState(
            run_id=run_id,
            session_key=session_key,
            idempotency_key=idempotency_key,
        )
        self._runs[run_id] = state
        self._idem[idempotency_key] = run_id

        from auraeve.bus.events import InboundMessage

        metadata: dict = {"run_id": run_id, "idempotency_key": idempotency_key}
        metadata["webui_user_id"] = user_id
        if display_name:
            metadata["webui_display_name"] = display_name

        msg = InboundMessage(
            channel="webui",
            sender_id=user_id,
            chat_id=session_key,
            content=message,
            metadata=metadata,
        )
        await self._bus.publish_inbound(msg)

        await self._broadcast(session_key, {
            "type": "chat.started",
            "runId": run_id,
            "sessionKey": session_key,
        })

        return run_id, "started"

    # ─── 终止 ──────────────────────────────────────────────────────

    async def abort(self, session_key: str, run_id: str | None = None) -> tuple[bool, str | None, str]:
        """软中止当前会话运行。返回 (ok, run_id, status)。"""
        target: RunState | None = None
        if run_id:
            target = self._runs.get(run_id)
        else:
            # 找到该 session 最新未完成的 run
            for state in reversed(list(self._runs.values())):
                if state.session_key == session_key and not state.done:
                    target = state
                    break

        if target is None:
            return False, run_id, "not_found"

        target.done = True
        target.aborted = True

        await self._broadcast(session_key, {
            "type": "chat.aborted",
            "runId": target.run_id,
            "sessionKey": session_key,
        })
        return True, target.run_id, "aborted"

    # ─── 出站消息回调（WebUIChannel 调用此处）─────────────────────

    async def on_outbound(self, msg: OutboundMessage) -> None:
        """WebUIChannel.send() 调用此处，将 Agent 回复广播给 SSE 订阅者。"""
        session_key = msg.chat_id

        # 找到该 session 最新运行的 run_id
        run_id = None
        for state in reversed(list(self._runs.values())):
            if state.session_key == session_key:
                run_id = state.run_id
                break

        await self._broadcast(session_key, {
            "type": "chat.final",
            "runId": run_id,
            "sessionKey": session_key,
            "content": msg.content,
        })

        # 标记该 run 完成
        if run_id and run_id in self._runs:
            self._runs[run_id].done = True

    # ─── SSE 订阅 ──────────────────────────────────────────────────

    async def subscribe(self, session_key: str) -> AsyncIterator[dict]:
        """返回异步生成器，持续产出该 session 的事件。"""
        q: asyncio.Queue = asyncio.Queue(maxsize=128)
        self._sse_queues.setdefault(session_key, []).append(q)
        try:
            while True:
                event = await q.get()
                if event is None:  # 哨兵：关闭
                    break
                yield event
        finally:
            queues = self._sse_queues.get(session_key, [])
            if q in queues:
                queues.remove(q)

    async def _broadcast(self, session_key: str, event: dict) -> None:
        for q in list(self._sse_queues.get(session_key, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"WebUI SSE 队列满，丢弃事件：{event.get('type')}")
