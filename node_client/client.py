"""
本地节点 WebSocket 客户端。

职责：
  - 连接服务器节点端口
  - 完成握手认证
  - 接收调用请求，分发给命令处理器
  - 返回执行结果
  - 断线自动重连（指数退避）
  - 上线时自动处理服务器推送的待机调用
"""

from __future__ import annotations

import asyncio
import json
import platform
import sys
from typing import Any

from loguru import logger

from node_client.commands import dispatch, list_commands

VERSION = "1.0.0"


class NodeClient:
    """
    本地节点客户端。

    使用方式：
        client = NodeClient(
            server_url="ws://your-server:8765",
            node_id="home-pc",
            token="your-token",
            display_name="家里电脑",
        )
        await client.run()
    """

    RECONNECT_BASE = 3.0    # 初始重连等待秒数
    RECONNECT_MAX = 60.0    # 最大重连等待秒数
    RECONNECT_FACTOR = 1.5  # 指数退避系数

    def __init__(
        self,
        server_url: str,
        node_id: str,
        token: str,
        display_name: str = "",
    ):
        self.server_url = server_url
        self.node_id = node_id
        self.token = token
        self.display_name = display_name or node_id
        self._running = False

    async def run(self) -> None:
        """主循环：连接服务器，断线后自动重连。"""
        self._running = True
        reconnect_wait = self.RECONNECT_BASE

        while self._running:
            try:
                await self._connect_and_run()
                # 正常断开（服务器主动关闭）不需要快速重连
                reconnect_wait = self.RECONNECT_BASE
            except Exception as e:
                logger.warning(f"连接异常：{e}")

            if not self._running:
                break

            logger.info(f"将在 {reconnect_wait:.0f}s 后重连...")
            await asyncio.sleep(reconnect_wait)
            reconnect_wait = min(reconnect_wait * self.RECONNECT_FACTOR, self.RECONNECT_MAX)

    def stop(self) -> None:
        self._running = False

    async def _connect_and_run(self) -> None:
        import websockets

        logger.info(f"正在连接：{self.server_url}")
        async with websockets.connect(
            self.server_url,
            ping_interval=30,
            ping_timeout=10,
            open_timeout=15,
        ) as ws:
            # ── 握手 ──────────────────────────────────────────────────────────
            await self._send(ws, {
                "type": "node.connect",
                "node_id": self.node_id,
                "token": self.token,
                "display_name": self.display_name,
                "platform": self._get_platform(),
                "version": VERSION,
                "commands": list_commands(),
            })

            raw = await asyncio.wait_for(ws.recv(), timeout=15.0)
            resp = json.loads(raw)

            if resp.get("type") == "node.connect.error":
                logger.error(f"握手失败：{resp.get('reason')}")
                return

            if resp.get("type") != "node.connect.ok":
                logger.error(f"握手响应未知：{resp}")
                return

            logger.info(f"已连接服务器，节点 ID：{self.node_id}")

            # ── 处理服务器推送的待机调用 ────────────────────────────────────────
            pending_calls = resp.get("pending_calls", [])
            if pending_calls:
                logger.info(f"收到 {len(pending_calls)} 条待机调用，开始执行...")
                for call in pending_calls:
                    asyncio.create_task(self._handle_invoke(ws, call))

            # ── 消息循环 ──────────────────────────────────────────────────────
            async for raw_msg in ws:
                try:
                    msg = json.loads(raw_msg)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type")

                if msg_type == "node.invoke":
                    asyncio.create_task(self._handle_invoke(ws, msg))

                elif msg_type == "node.pong":
                    pass  # 心跳回包，忽略

                else:
                    logger.debug(f"未知消息类型：{msg_type}")

    async def _handle_invoke(self, ws, msg: dict[str, Any]) -> None:
        """处理单条调用请求，执行命令并返回结果。"""
        call_id = msg.get("call_id", "")
        command = msg.get("command", "")
        params = msg.get("params") or {}
        timeout_ms = int(msg.get("timeout_ms", 60_000))

        logger.info(f"执行命令：{command}（call_id={call_id}）")

        try:
            ok, output, error = await asyncio.wait_for(
                dispatch(command, params),
                timeout=timeout_ms / 1000,
            )
        except asyncio.TimeoutError:
            ok, output, error = False, "", f"命令超时（{timeout_ms}ms）"
        except Exception as e:
            ok, output, error = False, "", f"内部错误：{e}"

        await self._send(ws, {
            "type": "node.result",
            "call_id": call_id,
            "ok": ok,
            "output": output,
            "error": error,
        })

        if ok:
            output_preview = output[:80].replace("\n", "↵") if output else "（无输出）"
            logger.info(f"命令完成：{command} → {output_preview}")
        else:
            logger.warning(f"命令失败：{command} → {error}")

    @staticmethod
    async def _send(ws, payload: dict) -> None:
        try:
            await ws.send(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            logger.debug(f"发送失败：{e}")

    @staticmethod
    def _get_platform() -> str:
        sys_name = platform.system().lower()
        if sys_name == "windows":
            return "windows"
        if sys_name == "darwin":
            return "macos"
        return "linux"
