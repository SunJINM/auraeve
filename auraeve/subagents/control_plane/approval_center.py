"""ApprovalCenter：审批中断点管理。"""

from __future__ import annotations

import asyncio
import time

from loguru import logger

from auraeve.subagents.data.models import Approval, ApprovalStatus, RiskLevel
from auraeve.subagents.data.repositories import SubagentDB


class ApprovalCenter:
    """审批中心：管理审批请求、人工确认、超时处理。"""

    def __init__(
        self,
        db: SubagentDB,
        timeout_s: int = 1800,
        bus_publish_outbound=None,
    ) -> None:
        self._db = db
        self._timeout_s = timeout_s
        self._bus_publish = bus_publish_outbound
        # approval_id -> asyncio.Future[str] (决策结果)
        self._pending_futures: dict[str, asyncio.Future] = {}

    async def request_approval(
        self,
        task_id: str,
        approval_id: str,
        action_desc: str,
        risk_level: str,
        context: dict | None = None,
        origin_channel: str = "",
        origin_chat_id: str = "",
    ) -> str:
        """创建审批请求并等待决策。返回 'approved' / 'rejected' / 'revised' / 'timed_out'。"""
        approval = Approval(
            approval_id=approval_id,
            task_id=task_id,
            action_desc=action_desc,
            risk_level=RiskLevel(risk_level),
        )
        self._db.save_approval(approval)

        # 通知用户
        await self._notify_user(approval, origin_channel, origin_chat_id)

        # 等待决策
        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        self._pending_futures[approval_id] = future

        try:
            result = await asyncio.wait_for(future, timeout=self._timeout_s)
            return result
        except asyncio.TimeoutError:
            self._db.decide_approval(approval_id, ApprovalStatus.TIMED_OUT)
            logger.warning(f"[approval] 审批 {approval_id} 超时")
            return "timed_out"
        finally:
            self._pending_futures.pop(approval_id, None)

    def decide(self, approval_id: str, decision: str, decided_by: str = "") -> bool:
        """处理审批决策（由外部调用，如 WebUI/渠道消息）。"""
        status_map = {
            "approve": ApprovalStatus.APPROVED,
            "approved": ApprovalStatus.APPROVED,
            "reject": ApprovalStatus.REJECTED,
            "rejected": ApprovalStatus.REJECTED,
            "revise": ApprovalStatus.REVISED,
            "revised": ApprovalStatus.REVISED,
        }
        status = status_map.get(decision)
        if not status:
            return False

        self._db.decide_approval(approval_id, status, decided_by)

        future = self._pending_futures.get(approval_id)
        if future and not future.done():
            future.set_result(decision)

        logger.info(f"[approval] 审批 {approval_id} 决策: {decision} by {decided_by}")
        return True

    async def _notify_user(
        self, approval: Approval, channel: str, chat_id: str
    ) -> None:
        if not self._bus_publish:
            return
        try:
            from auraeve.bus.events import OutboundMessage
            content = (
                f"⏸️ **审批请求**\n\n"
                f"任务: {approval.task_id}\n"
                f"动作: {approval.action_desc}\n"
                f"风险等级: {approval.risk_level.value}\n\n"
                f"请回复 `approve {approval.approval_id}` 批准，"
                f"`reject {approval.approval_id}` 拒绝。"
            )
            await self._bus_publish(OutboundMessage(
                channel=channel or "webui",
                chat_id=chat_id or "direct",
                content=content,
            ))
        except Exception as e:
            logger.error(f"[approval] 通知用户失败: {e}")
