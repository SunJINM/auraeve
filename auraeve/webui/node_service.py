"""NodeWebService：远程节点控制后端服务。"""

from __future__ import annotations

import asyncio
import time
from typing import Any, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from auraeve.subagents.control_plane.orchestrator import TaskOrchestrator


class NodeWebService:
    """提供节点、任务、审批、记忆增量的查询与操作接口。"""

    def __init__(self, orchestrator: "TaskOrchestrator") -> None:
        self._orch = orchestrator
        self._db = orchestrator._db
        self._event_queues: list[asyncio.Queue] = []

    # ── 节点管理 ────────────────────────────────────────────────────────────

    def list_nodes(self) -> dict[str, Any]:
        nodes = self._db.get_all_nodes()
        items = []
        for n in nodes:
            scores = self._db.get_capability_scores(n.node_id)
            running = self._db.get_running_count(n.node_id)
            items.append({
                "nodeId": n.node_id,
                "displayName": n.display_name,
                "platform": n.platform,
                "capabilities": n.capabilities,
                "isOnline": n.is_online,
                "connectedAt": n.connected_at,
                "disconnectedAt": n.disconnected_at,
                "runningTasks": running,
                "capabilityScores": [
                    {
                        "domain": s.capability_domain,
                        "score": round(s.score, 3),
                        "successCount": s.success_count,
                        "failCount": s.fail_count,
                        "avgDurationS": round(s.avg_duration_s, 2),
                    }
                    for s in scores
                ],
            })
        online = sum(1 for n in nodes if n.is_online)
        return {"ok": True, "nodes": items, "onlineCount": online, "totalCount": len(items)}

    def get_node_detail(self, node_id: str) -> dict[str, Any]:
        node = self._db.get_node(node_id)
        if not node:
            return {"ok": False, "message": f"节点 {node_id} 不存在"}
        scores = self._db.get_capability_scores(node_id)
        tasks = self._db.list_tasks(node_id=node_id, limit=50)
        return {
            "ok": True,
            "node": {
                "nodeId": node.node_id,
                "displayName": node.display_name,
                "platform": node.platform,
                "capabilities": node.capabilities,
                "isOnline": node.is_online,
                "connectedAt": node.connected_at,
                "disconnectedAt": node.disconnected_at,
            },
            "capabilityScores": [
                {
                    "domain": s.capability_domain,
                    "score": round(s.score, 3),
                    "successCount": s.success_count,
                    "failCount": s.fail_count,
                    "avgDurationS": round(s.avg_duration_s, 2),
                }
                for s in scores
            ],
            "tasks": [self._task_to_dict(t) for t in tasks],
        }

    def disconnect_node(self, node_id: str) -> dict[str, Any]:
        node = self._db.get_node(node_id)
        if not node:
            return {"ok": False, "message": f"节点 {node_id} 不存在"}
        if node_id == "local":
            return {"ok": False, "message": "不能断开本地节点"}
        self._orch.on_remote_disconnect(node_id)
        return {"ok": True, "message": f"节点 {node_id} 已断开"}

    # ── 任务管理 ────────────────────────────────────────────────────────────

    def list_tasks(
        self,
        status: str | None = None,
        node_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        from auraeve.subagents.data.models import TaskStatus
        ts = TaskStatus(status) if status else None
        tasks = self._db.list_tasks(status=ts, node_id=node_id or None, limit=limit)
        return {
            "ok": True,
            "tasks": [self._task_to_dict(t) for t in tasks],
            "total": len(tasks),
        }

    def get_task_detail(self, task_id: str) -> dict[str, Any]:
        task = self._db.get_task(task_id)
        if not task:
            return {"ok": False, "message": f"任务 {task_id} 不存在"}
        events = self._db.get_events(task_id)
        return {
            "ok": True,
            "task": self._task_to_dict(task),
            "events": [
                {
                    "seq": e.seq,
                    "eventType": e.event_type,
                    "payload": e.payload,
                    "traceId": e.trace_id,
                    "spanId": e.span_id,
                    "createdAt": e.created_at,
                }
                for e in events
            ],
        }

    async def pause_task(self, task_id: str) -> dict[str, Any]:
        msg = await self._orch.pause_task(task_id)
        return {"ok": "已暂停" in msg, "message": msg}

    async def resume_task(self, task_id: str) -> dict[str, Any]:
        msg = await self._orch.resume_task(task_id)
        return {"ok": "已恢复" in msg, "message": msg}

    async def cancel_task(self, task_id: str, reason: str = "webui_cancel") -> dict[str, Any]:
        msg = await self._orch.cancel_task(task_id, reason)
        return {"ok": "已取消" in msg, "message": msg}

    async def steer_task(self, task_id: str, message: str) -> dict[str, Any]:
        msg = await self._orch.steer_task(task_id, message)
        return {"ok": "已发送" in msg, "message": msg}

    async def submit_task(
        self,
        goal: str,
        priority: int = 5,
        assigned_node_id: str = "",
        origin_channel: str = "",
        origin_chat_id: str = "",
    ) -> dict[str, Any]:
        try:
            task = await self._orch.submit_task(
                goal=goal,
                priority=priority,
                assigned_node_id=assigned_node_id,
                origin_channel=origin_channel,
                origin_chat_id=origin_chat_id,
            )
            return {"ok": True, "taskId": task.task_id, "message": "任务已提交"}
        except RuntimeError as e:
            return {"ok": False, "message": str(e)}

    # ── 审批中心 ────────────────────────────────────────────────────────────

    def list_approvals(self, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        from auraeve.subagents.data.models import ApprovalStatus
        st = ApprovalStatus(status) if status else None
        approvals = self._db.list_approvals(status=st, limit=limit)
        return {
            "ok": True,
            "approvals": [
                {
                    "approvalId": a.approval_id,
                    "taskId": a.task_id,
                    "actionDesc": a.action_desc,
                    "riskLevel": a.risk_level.value,
                    "status": a.status.value,
                    "decidedBy": a.decided_by,
                    "decidedAt": a.decided_at,
                    "createdAt": a.created_at,
                }
                for a in approvals
            ],
            "total": len(approvals),
        }

    def decide_approval(self, approval_id: str, decision: str, decided_by: str = "webui") -> dict[str, Any]:
        ok = self._orch.decide_approval(approval_id, decision, decided_by)
        return {"ok": ok, "message": "审批已处理" if ok else "审批处理失败"}

    # ── 记忆增量 ────────────────────────────────────────────────────────────

    def list_deltas(
        self,
        merge_status: str | None = None,
        node_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        from auraeve.subagents.data.models import MergeStatus
        ms = MergeStatus(merge_status) if merge_status else None
        deltas = self._db.list_deltas(merge_status=ms, node_id=node_id or None, limit=limit)
        return {
            "ok": True,
            "deltas": [
                {
                    "deltaId": d.delta_id,
                    "taskId": d.task_id,
                    "nodeId": d.node_id,
                    "deltaType": d.delta_type.value,
                    "content": d.content[:500],
                    "confidence": d.confidence,
                    "mergeStatus": d.merge_status.value,
                    "createdAt": d.created_at,
                }
                for d in deltas
            ],
            "total": len(deltas),
        }

    def trigger_merge(self) -> dict[str, Any]:
        try:
            self._orch._try_merge_memory()
            return {"ok": True, "message": "记忆合并已触发"}
        except Exception as e:
            return {"ok": False, "message": f"合并失败: {e}"}

    # ── SSE 事件流 ──────────────────────────────────────────────────────────

    async def subscribe(self):
        """SSE 事件生成器，推送节点/任务状态变化。"""
        queue: asyncio.Queue = asyncio.Queue()
        self._event_queues.append(queue)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield event
                except asyncio.TimeoutError:
                    yield {"type": "ping"}
        finally:
            self._event_queues.remove(queue)

    def broadcast_event(self, event: dict[str, Any]) -> None:
        for q in self._event_queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    # ── 统计概览 ────────────────────────────────────────────────────────────

    def get_overview(self) -> dict[str, Any]:
        from auraeve.subagents.data.models import TaskStatus, ApprovalStatus as AS
        nodes = self._db.get_all_nodes()
        online = sum(1 for n in nodes if n.is_online)
        running = self._db.get_running_count()
        pending_approvals = len(self._db.list_approvals(status=AS.PENDING, limit=999))
        pending_deltas = len(self._db.get_pending_deltas(limit=999))

        # 各状态任务统计
        status_counts = {}
        for s in TaskStatus:
            count = len(self._db.list_tasks(status=s, limit=9999))
            if count > 0:
                status_counts[s.value] = count

        return {
            "ok": True,
            "onlineNodes": online,
            "totalNodes": len(nodes),
            "runningTasks": running,
            "pendingApprovals": pending_approvals,
            "pendingDeltas": pending_deltas,
            "taskStatusCounts": status_counts,
        }

    # ── 工具方法 ────────────────────────────────────────────────────────────

    @staticmethod
    def _task_to_dict(t) -> dict[str, Any]:
        return {
            "taskId": t.task_id,
            "goal": t.goal,
            "assignedNodeId": t.assigned_node_id,
            "priority": t.priority,
            "status": t.status.value,
            "dependsOn": t.depends_on,
            "budget": t.budget.to_dict(),
            "policyProfile": t.policy_profile,
            "result": t.result[:500] if t.result else "",
            "compensateAction": t.compensate_action,
            "traceId": t.trace_id,
            "originChannel": t.origin_channel,
            "originChatId": t.origin_chat_id,
            "createdAt": t.created_at,
            "updatedAt": t.updated_at,
        }
