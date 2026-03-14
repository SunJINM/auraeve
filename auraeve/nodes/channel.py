"""
节点 WebSocket 服务器渠道。

职责：
  - 监听指定端口，接受本地节点的 WebSocket 连接
  - 完成握手认证（令牌验证）
  - 将节点注册到 NodeManager
  - 转发调用结果、处理节点发来的事件
  - 节点断开后从 NodeManager 注销
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from loguru import logger

from auraeve.nodes.manager import NodeManager, NodeSession


@dataclass
class NodeChannelConfig:
    host: str = "0.0.0.0"
    port: int = 8765
    ping_interval: float = 30.0   # WebSocket 心跳间隔（秒）
    ping_timeout: float = 10.0    # 心跳无响应超时（秒）


class NodeChannel:
    """
    节点 WebSocket 服务器。

    协议（JSON 消息）：

    节点 → 服务器（握手）:
      {"type": "node.connect", "node_id": "...", "token": "...",
       "display_name": "...", "platform": "...", "version": "...",
       "commands": [...]}

    服务器 → 节点（握手响应）:
      {"type": "node.connect.ok", "pending_calls": [...]}
      {"type": "node.connect.error", "reason": "..."}

    服务器 → 节点（调用）:
      {"type": "node.invoke", "call_id": "...", "command": "...",
       "params": {...}, "timeout_ms": 30000}

    节点 → 服务器（调用结果）:
      {"type": "node.result", "call_id": "...", "ok": true/false,
       "output": "...", "error": "..."}
    """

    def __init__(self, config: NodeChannelConfig, manager: NodeManager):
        self.config = config
        self.manager = manager
        self._server = None
        self._running = False

    async def start(self) -> None:
        import websockets

        self._running = True
        logger.info(f"节点服务器启动：ws://{self.config.host}:{self.config.port}")

        async with websockets.serve(
            self._handle_connection,
            self.config.host,
            self.config.port,
            ping_interval=self.config.ping_interval,
            ping_timeout=self.config.ping_timeout,
        ) as server:
            self._server = server
            await asyncio.Future()  # 永久等待，直到外部 cancel

    async def stop(self) -> None:
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_connection(self, ws) -> None:
        """处理单个节点连接的完整生命周期。"""
        node_id: str | None = None
        try:
            # ── 握手 ──────────────────────────────────────────────────────────
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=15.0)
            except asyncio.TimeoutError:
                await self._send(ws, {"type": "node.connect.error", "reason": "握手超时"})
                return

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await self._send(ws, {"type": "node.connect.error", "reason": "无效 JSON"})
                return

            if msg.get("type") != "node.connect":
                await self._send(ws, {"type": "node.connect.error", "reason": "期望 node.connect 消息"})
                return

            node_id = str(msg.get("node_id", "")).strip()
            token = str(msg.get("token", "")).strip()
            display_name = str(msg.get("display_name", node_id))
            platform = str(msg.get("platform", "unknown"))
            version = str(msg.get("version", ""))
            commands = msg.get("commands", [])

            if not node_id or not token:
                await self._send(ws, {"type": "node.connect.error", "reason": "node_id 和 token 不能为空"})
                return

            if not self.manager.verify_token(node_id, token):
                logger.warning(f"节点 {node_id} 认证失败（token 不匹配）")
                await self._send(ws, {"type": "node.connect.error", "reason": "认证失败"})
                return

            # ── 注册会话 ──────────────────────────────────────────────────────
            async def _send_to_node(payload: dict) -> None:
                await self._send(ws, payload)

            session = NodeSession(
                node_id=node_id,
                display_name=display_name,
                platform=platform,
                version=version,
                commands=commands if isinstance(commands, list) else [],
                send=_send_to_node,
            )
            pending_calls = self.manager.register_session(session)

            # 握手成功，把待机调用一并发过去
            await self._send(ws, {
                "type": "node.connect.ok",
                "pending_calls": [
                    {
                        "call_id": c.call_id,
                        "command": c.command,
                        "params": c.params,
                        "timeout_ms": c.timeout_ms,
                    }
                    for c in pending_calls
                ],
            })
            logger.info(f"节点 {node_id}（{display_name}）握手完成，待机调用 {len(pending_calls)} 条")

            # ── 消息循环 ──────────────────────────────────────────────────────
            async for raw_msg in ws:
                try:
                    data = json.loads(raw_msg)
                except json.JSONDecodeError:
                    logger.warning(f"节点 {node_id} 发来无效 JSON，忽略")
                    continue

                msg_type = data.get("type")

                if msg_type == "node.result":
                    call_id = data.get("call_id", "")
                    result = {
                        "ok": data.get("ok", False),
                        "output": data.get("output", ""),
                        "error": data.get("error", ""),
                        "call_id": call_id,
                    }
                    found = self.manager.ack_invoke_result(call_id, result)
                    if not found:
                        logger.debug(f"节点 {node_id} 返回结果但对应调用已超时：{call_id}")

                elif msg_type == "node.ping":
                    await self._send(ws, {"type": "node.pong"})

                else:
                    logger.debug(f"节点 {node_id} 未知消息类型：{msg_type}")

        except Exception as e:
            import websockets.exceptions as wse
            if isinstance(e, (wse.ConnectionClosed, wse.ConnectionClosedOK, wse.ConnectionClosedError)):
                pass  # 正常断开，不打印错误
            else:
                logger.error(f"节点连接异常：{e}")
        finally:
            if node_id:
                self.manager.unregister_session(node_id)

    @staticmethod
    async def _send(ws, payload: dict) -> None:
        try:
            await ws.send(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass
