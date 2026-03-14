"""
节点管理器：维护已连接节点的注册表、配对令牌存储、待机队列。

架构：
  - NodeRegistry：内存中的在线节点表（节点 ID → NodeSession）
  - PairingStore：磁盘持久化的配对令牌（JSON 文件）
  - PendingQueue：节点离线时缓存的待执行调用
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from auraeve.config.stores import save_json_file_atomic

# ─────────────────────────────────────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NodeSession:
    """在线节点的运行时会话信息。"""
    node_id: str
    display_name: str
    platform: str                          # windows / linux / macos
    version: str
    commands: list[str]                    # 节点声明支持的命令列表
    connected_at: float = field(default_factory=time.time)
    send: Any = None                       # async callable: send(payload: dict) -> None


@dataclass
class PairedNode:
    """已配对节点的持久化记录。"""
    node_id: str
    token: str
    display_name: str
    platform: str
    created_at: float
    approved_at: float
    last_connected_at: float = 0.0


@dataclass
class PendingCall:
    """节点离线时入队的待机调用。"""
    call_id: str
    node_id: str
    command: str
    params: dict[str, Any]
    enqueued_at: float = field(default_factory=time.time)
    timeout_ms: int = 30_000


# ─────────────────────────────────────────────────────────────────────────────
# 配对存储（磁盘持久化）
# ─────────────────────────────────────────────────────────────────────────────

class PairingStore:
    """
    持久化已配对节点的令牌信息。
    存储路径：<stateDir>/nodes/paired.json
    """

    def __init__(self, store_dir: Path):
        self._path = store_dir / "paired.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._nodes: dict[str, PairedNode] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for item in data:
                n = PairedNode(**item)
                self._nodes[n.node_id] = n
            logger.info(f"节点配对记录加载：{len(self._nodes)} 个已配对节点")
        except Exception as e:
            logger.warning(f"加载节点配对记录失败：{e}")

    def _save(self) -> None:
        try:
            data = [vars(n) for n in self._nodes.values()]
            save_json_file_atomic(self._path, data)
        except Exception as e:
            logger.warning(f"保存节点配对记录失败：{e}")

    def add(self, node: PairedNode) -> None:
        self._nodes[node.node_id] = node
        self._save()

    def get(self, node_id: str) -> PairedNode | None:
        return self._nodes.get(node_id)

    def verify_token(self, node_id: str, token: str) -> bool:
        node = self._nodes.get(node_id)
        return node is not None and node.token == token

    def update_last_connected(self, node_id: str) -> None:
        node = self._nodes.get(node_id)
        if node:
            node.last_connected_at = time.time()
            self._save()

    def remove(self, node_id: str) -> bool:
        if node_id in self._nodes:
            del self._nodes[node_id]
            self._save()
            return True
        return False

    def list_all(self) -> list[PairedNode]:
        return list(self._nodes.values())


# ─────────────────────────────────────────────────────────────────────────────
# 待机队列
# ─────────────────────────────────────────────────────────────────────────────

class PendingQueue:
    """
    节点离线时缓存待执行的调用，节点上线后自动拉取。

    限制：
      - 每个节点最多 64 条待机
      - 超过 10 分钟自动过期丢弃
    """

    MAX_PER_NODE = 64
    TTL_SECONDS = 600  # 10 分钟

    def __init__(self):
        self._queues: dict[str, list[PendingCall]] = {}

    def enqueue(self, call: PendingCall) -> bool:
        """入队，返回 True 表示成功，False 表示队列已满。"""
        self._evict(call.node_id)
        q = self._queues.setdefault(call.node_id, [])
        if len(q) >= self.MAX_PER_NODE:
            logger.warning(f"节点 {call.node_id} 待机队列已满，丢弃调用 {call.call_id}")
            return False
        q.append(call)
        logger.debug(f"节点 {call.node_id} 待机调用入队：{call.command}（队列长度 {len(q)}）")
        return True

    def pull(self, node_id: str) -> list[PendingCall]:
        """拉取并清空指定节点的所有待机调用（已过期的跳过）。"""
        self._evict(node_id)
        calls = self._queues.pop(node_id, [])
        if calls:
            logger.info(f"节点 {node_id} 上线，拉取 {len(calls)} 条待机调用")
        return calls

    def _evict(self, node_id: str) -> None:
        """清除过期条目。"""
        now = time.time()
        q = self._queues.get(node_id, [])
        fresh = [c for c in q if now - c.enqueued_at < self.TTL_SECONDS]
        if len(fresh) != len(q):
            logger.debug(f"节点 {node_id} 过期待机调用清理：{len(q) - len(fresh)} 条")
        if fresh:
            self._queues[node_id] = fresh
        else:
            self._queues.pop(node_id, None)

    def depth(self, node_id: str) -> int:
        return len(self._queues.get(node_id, []))


# ─────────────────────────────────────────────────────────────────────────────
# 节点管理器
# ─────────────────────────────────────────────────────────────────────────────

class NodeManager:
    """
    节点管理器：统一管理节点注册、认证、调用分发。

    生命周期：
      register_session()   → 节点 WebSocket 握手成功后调用
      unregister_session() → 节点断开后调用
      invoke()             → Agent 向节点发起调用（离线时自动入队）
      ack_invoke_result()  → 节点返回调用结果时调用
    """

    INVOKE_TIMEOUT = 60.0  # 在线节点调用超时（秒）

    def __init__(self, store_dir: Path):
        self._pairing = PairingStore(store_dir)
        self._pending = PendingQueue()
        self._sessions: dict[str, NodeSession] = {}  # node_id → NodeSession
        self._pending_futures: dict[str, asyncio.Future] = {}  # call_id → Future

    # ── 配对管理 ─────────────────────────────────────────────────────────────

    def generate_token(self) -> str:
        """生成一个安全随机令牌（64 字节 hex）。"""
        return secrets.token_hex(32)

    def register_paired_node(
        self,
        node_id: str,
        token: str,
        display_name: str,
        platform: str,
    ) -> PairedNode:
        """持久化注册一个已配对节点（通常由管理员手动或通过配置文件触发）。"""
        node = PairedNode(
            node_id=node_id,
            token=token,
            display_name=display_name,
            platform=platform,
            created_at=time.time(),
            approved_at=time.time(),
        )
        self._pairing.add(node)
        logger.info(f"节点已配对：{node_id}（{display_name}，{platform}）")
        return node

    def verify_token(self, node_id: str, token: str) -> bool:
        return self._pairing.verify_token(node_id, token)

    def get_paired_node(self, node_id: str) -> PairedNode | None:
        return self._pairing.get(node_id)

    def list_paired_nodes(self) -> list[PairedNode]:
        return self._pairing.list_all()

    def remove_paired_node(self, node_id: str) -> bool:
        return self._pairing.remove(node_id)

    # ── 会话管理 ─────────────────────────────────────────────────────────────

    def register_session(self, session: NodeSession) -> list[PendingCall]:
        """
        节点连接握手成功后注册会话，并返回待机队列中缓存的调用列表。
        调用方负责将这些待机调用发送给节点。
        """
        self._sessions[session.node_id] = session
        self._pairing.update_last_connected(session.node_id)
        logger.info(
            f"节点上线：{session.node_id}（{session.display_name}，{session.platform}），"
            f"支持命令：{len(session.commands)} 个"
        )
        pending = self._pending.pull(session.node_id)
        return pending

    def unregister_session(self, node_id: str) -> None:
        self._sessions.pop(node_id, None)
        logger.info(f"节点下线：{node_id}")

    def get_session(self, node_id: str) -> NodeSession | None:
        return self._sessions.get(node_id)

    def list_sessions(self) -> list[NodeSession]:
        return list(self._sessions.values())

    def is_online(self, node_id: str) -> bool:
        return node_id in self._sessions

    # ── 调用接口 ─────────────────────────────────────────────────────────────

    async def invoke(
        self,
        node_id: str,
        command: str,
        params: dict[str, Any] | None = None,
        timeout_ms: int = 60_000,
    ) -> dict[str, Any]:
        """
        向节点发起调用。

        - 节点在线：直接发送并等待结果（最长 timeout_ms ms）
        - 节点离线：调用入队，返回 {"ok": false, "queued": true, "call_id": "..."}
        """
        call_id = str(uuid.uuid4())
        params = params or {}

        session = self._sessions.get(node_id)
        if session is None:
            # 节点离线，入待机队列
            call = PendingCall(
                call_id=call_id,
                node_id=node_id,
                command=command,
                params=params,
                timeout_ms=timeout_ms,
            )
            queued = self._pending.enqueue(call)
            return {
                "ok": False,
                "queued": queued,
                "call_id": call_id,
                "reason": "节点当前不在线，调用已入队" if queued else "节点不在线且待机队列已满",
            }

        # 节点在线，异步等待结果
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_futures[call_id] = future

        payload = {
            "type": "node.invoke",
            "call_id": call_id,
            "command": command,
            "params": params,
            "timeout_ms": timeout_ms,
        }

        try:
            await session.send(payload)
            result = await asyncio.wait_for(future, timeout=timeout_ms / 1000)
            return result
        except asyncio.TimeoutError:
            logger.warning(f"节点 {node_id} 调用超时：{command}（call_id={call_id}）")
            return {"ok": False, "reason": f"调用超时（{timeout_ms}ms）", "call_id": call_id}
        except Exception as e:
            logger.error(f"节点 {node_id} 调用异常：{e}")
            return {"ok": False, "reason": str(e), "call_id": call_id}
        finally:
            self._pending_futures.pop(call_id, None)

    def ack_invoke_result(self, call_id: str, result: dict[str, Any]) -> bool:
        """
        节点返回调用结果时调用，解除对应 Future 的等待。
        返回 True 表示找到了等待中的 Future，False 表示超时后已被清理。
        """
        future = self._pending_futures.get(call_id)
        if future and not future.done():
            future.set_result(result)
            return True
        return False

    # ── 汇总信息 ─────────────────────────────────────────────────────────────

    def describe(self) -> list[dict[str, Any]]:
        """返回所有节点（含离线）的描述列表，用于 Agent 工具展示。"""
        result = []
        for paired in self._pairing.list_all():
            session = self._sessions.get(paired.node_id)
            result.append({
                "node_id": paired.node_id,
                "display_name": paired.display_name,
                "platform": paired.platform,
                "online": session is not None,
                "commands": session.commands if session else [],
                "pending_calls": self._pending.depth(paired.node_id),
                "last_connected_at": paired.last_connected_at,
            })
        return result
