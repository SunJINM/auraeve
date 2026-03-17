"""WebSocket 服务端：母体侧远程子体连接管理。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from auraeve.subagents.protocol.codec import encode, decode
from auraeve.subagents.protocol.messages import (
    NodeConnectOkMsg,
    NodeConnectErrorMsg,
    TaskProgressMsg,
    TaskAlertMsg,
    TaskDoneMsg,
    TaskApprovalRequestMsg,
    PeerRequestMsg,
    PeerMessageMsg,
)

if TYPE_CHECKING:
    from auraeve.subagents.control_plane.orchestrator import TaskOrchestrator
    from .auth import TokenAuth


class SubAgentWSServer:
    """母体侧 WebSocket 服务端。

    每个远程子体连接后经过握手认证，后续消息路由到 TaskOrchestrator。
    """

    def __init__(
        self,
        orchestrator: "TaskOrchestrator",
        auth: "TokenAuth",
        host: str = "0.0.0.0",
        port: int = 9800,
        ping_interval: int = 30,
        ping_timeout: int = 10,
    ) -> None:
        self._orchestrator = orchestrator
        self._auth = auth
        self._host = host
        self._port = port
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._connections: dict[str, object] = {}  # node_id -> websocket
        self._server = None

    async def start(self) -> None:
        try:
            import websockets
        except ImportError:
            logger.error("[ws_server] websockets 未安装，远程子体不可用")
            return

        self._server = await websockets.serve(
            self._handle_connection,
            self._host,
            self._port,
            ping_interval=self._ping_interval,
            ping_timeout=self._ping_timeout,
        )
        logger.info(f"[ws_server] 子体 WebSocket 服务启动: {self._host}:{self._port}")

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("[ws_server] 子体 WebSocket 服务已停止")

    async def _handle_connection(self, websocket, path=None) -> None:
        node_id = ""
        try:
            node_id = await self._handshake(websocket)
            if not node_id:
                return

            self._connections[node_id] = websocket

            # 注册发送回调
            async def sender(data: str) -> None:
                await websocket.send(data)

            self._orchestrator.register_remote_sender(node_id, sender)

            # 通知上线
            # on_remote_connect 在握手阶段已调用

            # 消息循环
            async for raw in websocket:
                await self._handle_message(node_id, raw)

        except Exception as e:
            logger.error(f"[ws_server] 连接异常 {node_id}: {e}")
        finally:
            if node_id:
                self._connections.pop(node_id, None)
                self._orchestrator.on_remote_disconnect(node_id)
                logger.info(f"[ws_server] 子体断开: {node_id}")

    async def _handshake(self, websocket) -> str:
        """握手认证，成功返回 node_id，失败返回空串。"""
        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=10)
        except asyncio.TimeoutError:
            await websocket.close(4001, "握手超时")
            return ""

        msg = decode(raw)
        if msg.get("type") != "node.connect":
            await websocket.send(encode(NodeConnectErrorMsg(reason="首条消息必须为 node.connect")))
            await websocket.close(4002, "协议错误")
            return ""

        node_id = msg.get("node_id", "")
        token = msg.get("token", "")

        if not self._auth.verify(node_id, token):
            await websocket.send(encode(NodeConnectErrorMsg(reason="认证失败")))
            await websocket.close(4003, "认证失败")
            return ""

        # 注册到编排器
        pending = await self._orchestrator.on_remote_connect(node_id, msg)

        await websocket.send(encode(NodeConnectOkMsg(
            assigned_trace_id=f"trace-{node_id}",
            pending_tasks=[{"task_id": t.task_id, "goal": t.goal} for t in pending],
        )))

        logger.info(f"[ws_server] 子体握手成功: {node_id}")
        return node_id

    async def _handle_message(self, node_id: str, raw: str | bytes) -> None:
        msg = decode(raw)
        msg_type = msg.get("type", "")

        if msg_type == "task.progress":
            await self._orchestrator.handle_progress(
                task_id=msg["task_id"],
                step=msg.get("step", 0),
                message=msg.get("message", ""),
                tool_calls=msg.get("tool_calls", 0),
                tokens_used=msg.get("tokens_used", 0),
            )
        elif msg_type == "task.alert":
            await self._orchestrator.handle_alert(
                task_id=msg["task_id"],
                level=msg.get("level", "warning"),
                message=msg.get("message", ""),
            )
        elif msg_type == "task.done":
            await self._orchestrator.handle_done(
                task_id=msg["task_id"],
                success=msg.get("success", True),
                result=msg.get("result", ""),
                artifacts=msg.get("artifacts", []),
                memory_deltas=msg.get("memory_deltas", []),
                experience=msg.get("experience"),
            )
        elif msg_type == "task.approval_request":
            await self._orchestrator.handle_approval_request(
                task_id=msg["task_id"],
                approval_id=msg["approval_id"],
                action_desc=msg.get("action_desc", ""),
                risk_level=msg.get("risk_level", "high"),
                context=msg.get("context", {}),
            )
        elif msg_type == "peer.request":
            logger.info(f"[ws_server] 子体间通信请求: {node_id} → {msg.get('target_node_id')}")
        elif msg_type == "peer.message":
            await self._route_peer_message(msg)
        elif msg_type == "pong":
            pass
        else:
            logger.warning(f"[ws_server] 未知消息类型: {msg_type} from {node_id}")

    async def _route_peer_message(self, msg: dict) -> None:
        """路由子体间消息。"""
        to_node = msg.get("to_node_id", "")
        ws = self._connections.get(to_node)
        if ws:
            await ws.send(encode(msg))
        else:
            logger.warning(f"[ws_server] 目标子体 {to_node} 不在线")
