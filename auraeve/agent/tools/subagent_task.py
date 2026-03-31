"""子体任务管理工具：替代旧 spawn 工具，接入统一编排器。"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from auraeve.agent.tools.base import Tool
from auraeve.subagents.data.models import STATUS_ICON

if TYPE_CHECKING:
    from auraeve.subagents.control_plane.orchestrator import TaskOrchestrator


class SubAgentTaskTool(Tool):
    """
    子体任务全生命周期管理工具。

    action 可选值：
    - spawn：派生子体任务
    - dag：提交 DAG 任务组
    - list：查询任务列表
    - status：查询任务详情
    - steer：向运行中任务推送引导消息
    - pause：暂停任务
    - resume：恢复任务
    - cancel：取消任务
    - approve：审批待审操作
    """

    def __init__(self, orchestrator: "TaskOrchestrator") -> None:
        self._orch = orchestrator
        self._origin_channel = "webui"
        self._origin_chat_id = "direct"

    def set_context(self, channel: str, chat_id: str) -> None:
        self._origin_channel = channel
        self._origin_chat_id = chat_id

    @property
    def name(self) -> str:
        return "subagent"

    @property
    def description(self) -> str:
        return (
            "子体任务全生命周期管理，支持本地与远程节点调度。\n"
            "\n"
            "【适合用子体的场景】\n"
            "- 预计需要多步工具调用、耗时较长（>30s）的任务\n"
            "- 多个独立子任务可以并行执行（如同时从多个角度分析同一问题）\n"
            "- 需要不同专业角色视角的分析（法律、舆情、技术等分工明确）\n"
            "- 需要大量搜索、抓取、处理后再汇总的信息收集任务\n"
            "- 需要在独立上下文中执行、避免污染当前会话的操作\n"
            "\n"
            "【不适合用子体的场景】\n"
            "- 简单问答或单步工具调用（直接执行即可，子体开销不值得）\n"
            "- 需要与用户实时交互、反复确认的任务\n"
            "- 当前上下文已有足够信息可以直接回答的请求\n"
            "- 极短任务（<10s）或只需调用一两个工具的操作\n"
            "\n"
            "action=spawn：派生子体在后台执行任务（可通过 assigned_node_id 指定远程节点）。\n"
            "action=dag：提交 DAG 任务组（tasks 为任务列表，支持依赖关系）。\n"
            "action=list：查询任务列表。\n"
            "action=status：查询任务详情（需 task_id）。\n"
            "action=steer：推送引导消息（需 task_id + message）。\n"
            "action=pause：暂停任务（需 task_id）。\n"
            "action=resume：恢复任务（需 task_id）。\n"
            "action=cancel：取消任务（需 task_id）。\n"
            "action=approve：审批操作（需 approval_id + decision）。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["spawn", "dag", "list", "status", "steer", "pause", "resume", "cancel", "approve"],
                    "description": "操作类型",
                },
                "goal": {
                    "type": "string",
                    "description": "（spawn）任务目标描述",
                },
                "priority": {
                    "type": "integer",
                    "description": "（spawn）优先级 1-9，默认 5",
                },
                "tasks": {
                    "type": "array",
                    "description": "（dag）任务列表，每项含 id/goal/depends_on/priority",
                    "items": {"type": "object"},
                },
                "task_id": {
                    "type": "string",
                    "description": "目标任务 ID",
                },
                "message": {
                    "type": "string",
                    "description": "（steer）引导消息内容",
                },
                "approval_id": {
                    "type": "string",
                    "description": "（approve）审批 ID",
                },
                "decision": {
                    "type": "string",
                    "enum": ["approve", "reject"],
                    "description": "（approve）审批决策",
                },
                "limit": {
                    "type": "integer",
                    "description": "（list）返回数量限制",
                },
                "assigned_node_id": {
                    "type": "string",
                    "description": "（spawn/dag）指定执行节点 ID（如 'work-pc'）；留空则由调度器自动选择最优节点",
                },
                "role_prompt": {
                    "type": "string",
                    "description": (
                        "（spawn）子体角色配置。在此描述子体的身份定位、背景知识、工具使用偏好、输出格式要求等。"
                        "例如：'你是一名资深法律分析师，专注于中国著作权法领域。分析时引用具体法条，"
                        "结论部分给出明确的风险等级（高/中/低）和建议行动。'"
                    ),
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str = "spawn",
        goal: str | None = None,
        priority: int = 5,
        tasks: list[dict] | None = None,
        task_id: str | None = None,
        message: str | None = None,
        approval_id: str | None = None,
        decision: str | None = None,
        limit: int = 20,
        assigned_node_id: str = "",
        role_prompt: str = "",
        **kwargs: Any,
    ) -> str:
        if action == "spawn":
            return await self._spawn(goal, priority, assigned_node_id, kwargs.get("agent_name", ""), role_prompt)
        elif action == "dag":
            return await self._dag(tasks)
        elif action == "list":
            return self._list(limit)
        elif action == "status":
            return self._status(task_id)
        elif action == "steer":
            return await self._steer(task_id, message)
        elif action == "pause":
            return await self._pause(task_id)
        elif action == "resume":
            return await self._resume(task_id)
        elif action == "cancel":
            return await self._cancel(task_id)
        elif action == "approve":
            return self._approve(approval_id, decision)
        return f"未知 action: {action}"

    async def _spawn(
        self,
        goal: str | None,
        priority: int,
        assigned_node_id: str = "",
        agent_name: str = "",
        role_prompt: str = "",
    ) -> str:
        if not goal:
            return "错误：spawn 需要 goal 参数"
        task = await self._orch.submit_task(
            goal=goal,
            priority=priority,
            origin_channel=self._origin_channel,
            origin_chat_id=self._origin_chat_id,
            assigned_node_id=assigned_node_id,
            agent_name=agent_name,
            role_prompt=role_prompt,
        )
        return f"任务已创建: {task.task_id}\n目标: {task.goal}\n状态: {STATUS_ICON.get(task.status, '')} {task.status.value}"

    async def _dag(self, tasks: list[dict] | None) -> str:
        if not tasks:
            return "错误：dag 需要 tasks 参数"
        created = await self._orch.submit_dag(tasks)
        lines = [f"DAG 已创建 {len(created)} 个任务："]
        for t in created:
            deps = f" (依赖: {', '.join(t.depends_on)})" if t.depends_on else ""
            lines.append(f"  {STATUS_ICON.get(t.status, '')} {t.task_id}: {t.goal}{deps}")
        return "\n".join(lines)

    def _list(self, limit: int) -> str:
        tasks = self._orch.list_tasks(limit=limit)
        if not tasks:
            return "当前没有子体任务。"
        lines = [f"共 {len(tasks)} 个任务："]
        for t in tasks:
            icon = STATUS_ICON.get(t.status, "")
            node = f" [{t.assigned_node_id}]" if t.assigned_node_id else ""
            lines.append(f"  {icon} {t.task_id}: {t.goal[:50]}{node} ({t.status.value})")
        return "\n".join(lines)

    def _status(self, task_id: str | None) -> str:
        if not task_id:
            return "错误：需要 task_id"
        task = self._orch.get_task(task_id)
        if not task:
            return f"任务 {task_id} 不存在"
        icon = STATUS_ICON.get(task.status, "")
        lines = [
            f"{icon} 任务: {task.task_id}",
            f"目标: {task.goal}",
            f"状态: {task.status.value}",
            f"节点: {task.assigned_node_id or '未分配'}",
            f"优先级: {task.priority}",
            f"结果: {task.result[:200]}" if task.result else "",
        ]
        return "\n".join(l for l in lines if l)

    async def _steer(self, task_id: str | None, message: str | None) -> str:
        if not task_id:
            return "错误：需要 task_id"
        if not message:
            return "错误：需要 message"
        result = await self._orch.steer_task(task_id, message)
        return result

    async def _pause(self, task_id: str | None) -> str:
        if not task_id:
            return "错误：需要 task_id"
        return await self._orch.pause_task(task_id)

    async def _resume(self, task_id: str | None) -> str:
        if not task_id:
            return "错误：需要 task_id"
        return await self._orch.resume_task(task_id)

    async def _cancel(self, task_id: str | None) -> str:
        if not task_id:
            return "错误：需要 task_id"
        return await self._orch.cancel_task(task_id)

    def _approve(self, approval_id: str | None, decision: str | None) -> str:
        if not approval_id:
            return "错误：需要 approval_id"
        if not decision:
            return "错误：需要 decision（approve/reject）"
        ok = self._orch.decide_approval(approval_id, decision)
        return f"审批 {approval_id} {'成功' if ok else '失败'}: {decision}"
