"""WebSocket 客户端：远程子体侧连接母体。"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Awaitable

from loguru import logger

from auraeve.subagents.protocol.codec import encode, decode
from auraeve.subagents.protocol.messages import (
    NodeConnectMsg,
    TaskProgressMsg,
    TaskAlertMsg,
    TaskDoneMsg,
    TaskApprovalRequestMsg,
    PongMsg,
)


class SubAgentWSClient:
    """远程子体侧 WebSocket 客户端。

    职责：连接母体、握手、接收任务、上报进度/结果。
    """

    def __init__(
        self,
        node_id: str,
        token: str,
        mother_url: str,
        display_name: str = "",
        platform: str = "",
        capabilities: list[dict] | None = None,
        on_task_assign: Callable[[dict], Awaitable[None]] | None = None,
        on_task_pause: Callable[[str], Awaitable[None]] | None = None,
        on_task_resume: Callable[[str], Awaitable[None]] | None = None,
        on_task_cancel: Callable[[str], Awaitable[None]] | None = None,
        on_approval_decide: Callable[[str, str], Awaitable[None]] | None = None,
        on_budget_adjust: Callable[[str, dict], Awaitable[None]] | None = None,
        reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 60.0,
    ) -> None:
        self._node_id = node_id
        self._token = token
        self._mother_url = mother_url
        self._display_name = display_name or node_id
        self._platform = platform
        self._capabilities = capabilities or []

        self._on_task_assign = on_task_assign
        self._on_task_pause = on_task_pause
        self._on_task_resume = on_task_resume
        self._on_task_cancel = on_task_cancel
        self._on_approval_decide = on_approval_decide
        self._on_budget_adjust = on_budget_adjust

        self._reconnect_delay = reconnect_delay
        self._max_reconnect_delay = max_reconnect_delay
        self._ws = None
        self._running = False

    async def connect(self) -> None:
        """连接母体并进入消息循环（自动重连）。"""
        try:
            import websockets
        except ImportError:
            logger.error("[ws_client] websockets 未安装")
            return

        self._running = True
        delay = self._reconnect_delay

        while self._running:
            try:
                async with websockets.connect(self._mother_url) as ws:
                    self._ws = ws
                    delay = self._reconnect_delay

                    # 握手
                    ok = await self._handshake(ws)
                    if not ok:
                        break

                    logger.info(f"[ws_client] 已连接母体: {self._mother_url}")

                    # 消息循环
                    async for raw in ws:
                        await self._handle_message(raw)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[ws_client] 连接断开: {e}，{delay:.0f}s 后重连")
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._max_reconnect_delay)
            finally:
                self._ws = None

    def disconnect(self) -> None:
        self._running = False

    async def _handshake(self, ws) -> bool:
        msg = NodeConnectMsg(
            node_id=self._node_id,
            token=self._token,
            display_name=self._display_name,
            platform=self._platform,
            capabilities=self._capabilities,
        )
        await ws.send(encode(msg))

        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        resp = decode(raw)

        if resp.get("type") == "node.connect.ok":
            pending = resp.get("pending_tasks", [])
            if pending:
                logger.info(f"[ws_client] 有 {len(pending)} 个待恢复任务")
                for t in pending:
                    if self._on_task_assign:
                        await self._on_task_assign(t)
            return True

        reason = resp.get("reason", "未知错误")
        logger.error(f"[ws_client] 握手失败: {reason}")
        return False

    async def _handle_message(self, raw: str | bytes) -> None:
        msg = decode(raw)
        msg_type = msg.get("type", "")

        if msg_type == "task.assign":
            if self._on_task_assign:
                await self._on_task_assign(msg)
        elif msg_type == "task.pause":
            if self._on_task_pause:
                await self._on_task_pause(msg["task_id"])
        elif msg_type == "task.resume":
            if self._on_task_resume:
                await self._on_task_resume(msg["task_id"])
        elif msg_type == "task.cancel":
            if self._on_task_cancel:
                await self._on_task_cancel(msg["task_id"])
        elif msg_type == "task.approval_decide":
            if self._on_approval_decide:
                await self._on_approval_decide(msg["approval_id"], msg["decision"])
        elif msg_type == "task.budget_adjust":
            if self._on_budget_adjust:
                await self._on_budget_adjust(msg["task_id"], msg.get("budget", {}))
        elif msg_type == "ping":
            await self._send(PongMsg())
        elif msg_type == "peer.message":
            logger.info(f"[ws_client] 收到子体间消息: {msg.get('from_node_id')}")
        else:
            logger.warning(f"[ws_client] 未知消息: {msg_type}")

    async def _send(self, msg: Any) -> bool:
        if not self._ws:
            return False
        try:
            await self._ws.send(encode(msg))
            return True
        except Exception as e:
            logger.error(f"[ws_client] 发送失败: {e}")
            return False

    # ── 上报接口 ──────────────────────────────────────────────────────────

    async def report_progress(
        self, task_id: str, step: int = 0, message: str = "",
        tool_calls: int = 0, tokens_used: int = 0,
    ) -> bool:
        return await self._send(TaskProgressMsg(
            task_id=task_id, step=step, message=message,
            tool_calls=tool_calls, tokens_used=tokens_used,
        ))

    async def report_alert(
        self, task_id: str, level: str = "warning", message: str = "",
    ) -> bool:
        return await self._send(TaskAlertMsg(
            task_id=task_id, level=level, message=message,
        ))

    async def report_done(
        self, task_id: str, success: bool = True, result: str = "",
        artifacts: list[dict] | None = None,
        memory_deltas: list[dict] | None = None,
        experience: dict | None = None,
    ) -> bool:
        return await self._send(TaskDoneMsg(
            task_id=task_id, success=success, result=result,
            artifacts=artifacts or [],
            memory_deltas=memory_deltas or [],
            experience=experience,
        ))

    async def request_approval(
        self, task_id: str, approval_id: str,
        action_desc: str = "", risk_level: str = "high",
        context: dict | None = None,
    ) -> bool:
        return await self._send(TaskApprovalRequestMsg(
            task_id=task_id, approval_id=approval_id,
            action_desc=action_desc, risk_level=risk_level,
            context=context or {},
        ))
