"""WebUI 聊天服务：管理聊天会话、历史、发送、终止与 SSE 事件分发。"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator

from loguru import logger

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.agent_runtime.command_types import QueuedCommand
from auraeve.bus.events import OutboundMessage
from auraeve.observability import get_observability
from auraeve.session.manager import SessionManager
from auraeve.webui.schemas import ChatTranscriptBlockEvent, ChatTranscriptDoneEvent


@dataclass
class RunState:
    run_id: str
    session_key: str
    idempotency_key: str
    done: bool = False
    aborted: bool = False
    seq: int = 0
    # 流式文本块状态：delta 到达时实时更新同一个 block
    streaming_block_id: str | None = None
    streaming_content: str = ""
    streaming_seq: int = 0


class ChatService:
    """
    聊天业务层。

    职责：
    - 历史加载（复用 SessionManager）
    - 发送消息（统一入 RuntimeCommandQueue）
    - 终止（软中止：标记 done/aborted）
    - SSE 事件队列管理（每个 sessionKey 对应一个广播队列）
    - 实时 transcript 事件推送（订阅 observability 的 runtime/tools/runtime/assistant 事件）
    """

    def __init__(
        self,
        session_manager: SessionManager,
        command_queue: RuntimeCommandQueue,
    ) -> None:
        self._sm = session_manager
        self._command_queue = command_queue
        # run_id -> RunState
        self._runs: dict[str, RunState] = {}
        # idempotency_key -> run_id （防重入）
        self._idem: dict[str, str] = {}
        # session_key -> list[asyncio.Queue]（SSE 订阅者）
        self._sse_queues: dict[str, list[asyncio.Queue]] = {}
        # obs 订阅 ID
        self._obs_sub_id: str | None = None
        self._obs_task: asyncio.Task | None = None

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

    def get_transcript_messages(self, session_key: str, limit: int = 200) -> list[dict[str, Any]]:
        """返回 transcript 投影所需的原始消息字段。"""
        session = self._sm.get_or_create(session_key)
        msgs = session.messages[-limit:] if limit else session.messages
        return [dict(msg) for msg in msgs]

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
        发布统一运行时命令，返回 (run_id, status)。
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

        metadata: dict = {"run_id": run_id, "idempotency_key": idempotency_key}
        metadata["webui_user_id"] = user_id

        self._command_queue.enqueue_command(
            QueuedCommand(
                session_key=session_key,
                source="webui",
                mode="prompt",
                priority="next",
                payload={
                    "content": message,
                    "channel": "webui",
                    "sender_id": user_id,
                    "chat_id": session_key,
                    "metadata": metadata,
                },
                origin={"kind": "user"},
            )
        )

        await self._broadcast(
            session_key,
            self._build_block_event(
                session_key=session_key,
                run_id=run_id,
                seq=self._next_seq(run_id),
                block={
                    "id": f"run_status:{run_id}:started",
                    "type": "run_status",
                    "status": "started",
                    "content": "run.started",
                    "timestamp": datetime.now().isoformat(),
                },
            ),
        )

        # 启动 obs 监听（如果尚未启动）
        self._ensure_obs_listener()

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

        await self._broadcast(
            session_key,
            self._build_block_event(
                session_key=session_key,
                run_id=target.run_id,
                seq=self._next_seq(target.run_id),
                block={
                    "id": f"run_status:{target.run_id}:aborted",
                    "type": "run_status",
                    "status": "aborted",
                    "content": "run.aborted",
                    "timestamp": datetime.now().isoformat(),
                },
            ),
        )
        await self._broadcast(
            session_key,
            self._build_done_event(
                session_key=session_key,
                run_id=target.run_id,
                seq=self._next_seq(target.run_id),
            ),
        )
        return True, target.run_id, "aborted"

    # ─── 出站消息回调（WebUIChannel 调用此处）─────────────────────

    async def on_outbound(self, msg: OutboundMessage) -> None:
        """WebUIChannel.send() 调用此处，将 Agent 回复广播给 SSE 订阅者。"""
        session_key = msg.chat_id

        run_id = str(msg.metadata.get("run_id") or "") or None
        state = self._runs.get(run_id) if run_id else None
        if state is None:
            state = self._latest_run_for_session(session_key)
            run_id = state.run_id if state else None

        await self._broadcast(
            session_key,
            self._build_block_event(
                session_key=session_key,
                run_id=run_id,
                seq=self._next_seq(run_id),
                block={
                    "id": f"assistant_text:{run_id or uuid.uuid4()}",
                    "type": "assistant_text",
                    "content": msg.content,
                    "timestamp": datetime.now().isoformat(),
                },
            ),
        )
        await self._broadcast(
            session_key,
            self._build_done_event(
                session_key=session_key,
                run_id=run_id,
                seq=self._next_seq(run_id),
            ),
        )

        # 标记该 run 完成
        if run_id and run_id in self._runs:
            self._runs[run_id].done = True

    # ─── Observability 实时 tool 事件监听 ──────────────────────────

    def _ensure_obs_listener(self) -> None:
        """确保 obs runtime 事件监听器已启动。"""
        if self._obs_task is not None and not self._obs_task.done():
            return
        try:
            obs = get_observability()
            if not obs.enabled:
                return
            self._obs_sub_id, queue = obs.subscribe(subsystems=["runtime/tools", "runtime/assistant"])
            self._obs_task = asyncio.create_task(self._obs_runtime_listener(queue))
        except Exception:
            logger.debug("无法启动 obs runtime 事件监听")

    async def _obs_runtime_listener(self, queue: asyncio.Queue) -> None:
        """持续消费 obs runtime 事件，实时推送 transcript block。"""
        try:
            while True:
                event = await queue.get()
                try:
                    subsystem = str(event.get("subsystem") or "")
                    if subsystem == "runtime/assistant":
                        await self._handle_assistant_event(event)
                    else:
                        await self._handle_tool_event(event)
                except Exception:
                    logger.debug(f"处理 runtime 事件异常: {event.get('message', '')}")
        except asyncio.CancelledError:
            pass
        finally:
            if self._obs_sub_id:
                try:
                    get_observability().unsubscribe(self._obs_sub_id)
                except Exception:
                    pass

    async def _handle_tool_event(self, event: dict[str, Any]) -> None:
        """将 obs tool 事件转化为 transcript tool_use block 推送。"""
        message = str(event.get("message") or "")
        attrs = event.get("attrs") or {}
        session_key = str(event.get("sessionKey") or "")
        if not session_key:
            return

        # 只处理 webui 会话
        state = self._latest_run_for_session(session_key)
        if state is None or state.done:
            return
        run_id = state.run_id

        tool_name = str(attrs.get("toolName") or "")
        tool_call_id = str(attrs.get("toolCallId") or "")
        block_id = f"tool_use:{tool_call_id or uuid.uuid4()}"
        parsed_args = self._parse_args_preview(attrs.get("argsPreview"))

        if message == "tool_call_started":
            await self._broadcast(
                session_key,
                self._build_block_event(
                    session_key=session_key,
                    run_id=run_id,
                    seq=self._next_seq(run_id),
                    block={
                        "id": block_id,
                        "type": "tool_use",
                        "toolCallId": tool_call_id,
                        "toolName": tool_name,
                        "arguments": parsed_args,
                        "result": None,
                        "status": "running",
                    },
                ),
            )

        elif message == "tool_call_completed":
            status_str = str(attrs.get("status") or "success")
            tool_status = "error" if status_str in ("failed", "timeout", "policy_denied", "hook_blocked") else "success"
            result_preview = str(attrs.get("resultPreview") or "")

            await self._broadcast(
                session_key,
                self._build_block_event(
                    session_key=session_key,
                    run_id=run_id,
                    seq=self._next_seq(run_id),
                    op="replace",
                    block={
                        "id": block_id,
                        "type": "tool_use",
                        "toolCallId": tool_call_id,
                        "toolName": tool_name,
                        "arguments": parsed_args,
                        "result": result_preview,
                        "status": tool_status,
                    },
                ),
            )

        elif message in ("tool_call_policy_denied", "tool_call_hook_blocked"):
            reason = str(attrs.get("reason") or message)
            await self._broadcast(
                session_key,
                self._build_block_event(
                    session_key=session_key,
                    run_id=run_id,
                    seq=self._next_seq(run_id),
                    op="replace",
                    block={
                        "id": block_id,
                        "type": "tool_use",
                        "toolCallId": tool_call_id,
                        "toolName": tool_name,
                        "arguments": parsed_args,
                        "result": reason,
                        "status": "error",
                    },
                ),
            )

    async def _handle_assistant_event(self, event: dict[str, Any]) -> None:
        """将 obs assistant 事件转化为 transcript assistant_text block 推送。

        支持两种消息类型：
        - assistant_text_delta：流式增量，实时更新同一个 block
        - assistant_text：完整内容，流结束后做最终 replace（或无流时新建）
        """
        message = str(event.get("message") or "")
        if message not in ("assistant_text_delta", "assistant_text"):
            return

        session_key = str(event.get("sessionKey") or "")
        if not session_key:
            return

        state = self._latest_run_for_session(session_key)
        if state is None or state.done:
            return
        run_id = state.run_id
        attrs = event.get("attrs") or {}

        if message == "assistant_text_delta":
            delta = str(attrs.get("delta") or "")
            if not delta:
                return

            if state.streaming_block_id is None:
                # 第一个 delta：分配 seq 并创建新 block
                state.streaming_seq = self._next_seq(run_id)
                state.streaming_block_id = f"assistant_text_stream:{run_id}:{state.streaming_seq}"
                state.streaming_content = delta
                op = "append"
            else:
                # 后续 delta：追加内容，替换同一个 block
                state.streaming_content += delta
                op = "replace"

            await self._broadcast(
                session_key,
                self._build_block_event(
                    session_key=session_key,
                    run_id=run_id,
                    seq=state.streaming_seq,
                    op=op,
                    block={
                        "id": state.streaming_block_id,
                        "type": "assistant_text",
                        "content": state.streaming_content,
                        "timestamp": datetime.now().isoformat(),
                    },
                ),
            )

        else:  # assistant_text（完整内容，流结束后触发）
            content = str(attrs.get("content") or "").strip()
            if not content:
                return

            if state.streaming_block_id is not None:
                # 已有流式 block：用完整内容做最终 replace，然后清空流式状态
                block_id = state.streaming_block_id
                seq = state.streaming_seq
                op = "replace"
                state.streaming_block_id = None
                state.streaming_content = ""
            else:
                # 无流式 block（模型未产生 delta）：新建
                seq = self._next_seq(run_id)
                block_id = f"assistant_text:{run_id}:{seq}"
                op = "append"

            await self._broadcast(
                session_key,
                self._build_block_event(
                    session_key=session_key,
                    run_id=run_id,
                    seq=seq,
                    op=op,
                    block={
                        "id": block_id,
                        "type": "assistant_text",
                        "content": content,
                        "timestamp": datetime.now().isoformat(),
                    },
                ),
            )

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

    def _latest_run_for_session(self, session_key: str) -> RunState | None:
        for state in reversed(list(self._runs.values())):
            if state.session_key == session_key:
                return state
        return None

    def _next_seq(self, run_id: str | None) -> int:
        if not run_id:
            return 0
        state = self._runs.get(run_id)
        if state is None:
            return 0
        seq = state.seq
        state.seq += 1
        return seq

    @staticmethod
    def _build_block_event(
        *,
        session_key: str,
        run_id: str | None,
        seq: int,
        block: dict[str, Any],
        op: str = "append",
    ) -> dict[str, Any]:
        return ChatTranscriptBlockEvent.model_validate(
            {
                "type": "transcript.block",
                "sessionKey": session_key,
                "runId": run_id,
                "seq": seq,
                "op": op,
                "block": block,
            }
        ).model_dump(mode="json", exclude_none=True)

    @staticmethod
    def _build_done_event(*, session_key: str, run_id: str | None, seq: int) -> dict[str, Any]:
        return ChatTranscriptDoneEvent.model_validate(
            {
                "type": "transcript.done",
                "sessionKey": session_key,
                "runId": run_id,
                "seq": seq,
            }
        ).model_dump(mode="json", exclude_none=True)

    @staticmethod
    def _parse_args_preview(raw_args: Any) -> Any:
        args_preview = str(raw_args or "")
        if not args_preview:
            return None
        try:
            return json.loads(args_preview)
        except Exception:
            return args_preview

    def get_runtime_status(self, session_key: str) -> dict[str, Any]:
        """返回指定会话最近一次运行的状态摘要。"""
        for state in reversed(list(self._runs.values())):
            if state.session_key != session_key:
                continue
            if state.aborted:
                status = "aborted"
            elif state.done:
                status = "completed"
            else:
                status = "running"
            return {
                "runId": state.run_id,
                "status": status,
                "done": state.done,
                "aborted": state.aborted,
            }
        return {"runId": None, "status": "idle", "done": True, "aborted": False}
