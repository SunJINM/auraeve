"""TaskOrchestrator：DAG 编排、拓扑调度、Saga 补偿、统一子体管理。"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, TYPE_CHECKING

from loguru import logger

from auraeve.subagents.data.models import (
    Task, TaskBudget, TaskStatus, NodeSession,
    MemoryDelta, DeltaType, MergeStatus,
    is_valid_transition, STATUS_ICON,
)
from auraeve.subagents.data.repositories import SubagentDB
from auraeve.subagents.runtime.capabilities import CapabilityRegistry
from .scheduler import Scheduler, SchedulerWeights
from .approval_center import ApprovalCenter
from .capability_tracker import CapabilityTracker
from .telemetry_hub import TelemetryHub, new_span_id

if TYPE_CHECKING:
    from auraeve.providers.base import LLMProvider
    from auraeve.bus.queue import MessageBus
    from auraeve.agent_runtime.tool_policy.engine import ToolPolicyEngine
    from .local_executor import LocalSubAgentExecutor


class TaskOrchestrator:
    """统一任务编排器。管理本地/远程子体的完整任务生命周期。"""

    def __init__(
        self,
        db: SubagentDB,
        provider: "LLMProvider",
        bus: "MessageBus",
        workspace: Path,
        policy: "ToolPolicyEngine",
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        max_iterations: int = 50,
        thinking_budget_tokens: int | None = None,
        max_global_tasks: int = 10,
        max_node_tasks: int = 3,
        approval_timeout_s: int = 1800,
        scheduler_weights: dict | None = None,
        tool_builder=None,
        execution_workspace: str | None = None,
    ) -> None:
        self._db = db
        self._provider = provider
        self._bus = bus
        self._workspace = workspace
        self._policy = policy
        self._model = model or provider.get_default_model()
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_iterations = max_iterations
        self._thinking_budget_tokens = thinking_budget_tokens
        self._max_global = max_global_tasks
        self._tool_builder = tool_builder
        self._execution_workspace = execution_workspace

        # 子模块
        self._tracker = CapabilityTracker(db)
        self._telemetry = TelemetryHub(db)
        self._approval = ApprovalCenter(
            db, timeout_s=approval_timeout_s,
            bus_publish_outbound=bus.publish_outbound,
        )
        weights = SchedulerWeights(**(scheduler_weights or {})) if scheduler_weights else None
        self._scheduler = Scheduler(db, self._tracker, weights, max_node_tasks)

        # 本地执行器（延迟初始化）
        self._local_executor: LocalSubAgentExecutor | None = None

        # 远程子体 WebSocket 发送回调: node_id -> send(msg_dict)
        self._remote_senders: dict[str, Any] = {}

        # 补偿任务 -> 原任务 ID 映射
        self._compensation_map: dict[str, str] = {}
        self._kernel_resume_callback = None
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._injected_task_ids: set[str] = set()

        # 记忆合并服务（延迟初始化）
        self._merge_service = None

        # 注册本地节点
        self._register_local_node()

    def _register_local_node(self) -> None:
        caps = CapabilityRegistry.default_local()
        self._db.upsert_node(NodeSession(
            node_id="local",
            display_name="本机",
            platform=sys.platform,
            capabilities=caps.to_json(),
            connected_at=time.time(),
            is_online=True,
        ))

    def register_kernel_resume(self, callback) -> None:
        """注册母体恢复执行回调。"""
        self._kernel_resume_callback = callback

    def _get_local_executor(self) -> "LocalSubAgentExecutor":
        if self._local_executor is None:
            from .local_executor import LocalSubAgentExecutor
            self._local_executor = LocalSubAgentExecutor(
                orchestrator=self,
                provider=self._provider,
                tool_builder=self._tool_builder or self._default_tool_builder,
                policy=self._policy,
                workspace=self._workspace,
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                max_iterations=self._max_iterations,
                thinking_budget_tokens=self._thinking_budget_tokens,
            )
        return self._local_executor

    def _default_tool_builder(self, task: Task):
        from auraeve.agent.tools.assembler import build_tool_registry
        from auraeve.agent.plan import PlanManager
        return build_tool_registry(
            profile="subagent",
            workspace=self._workspace,
            restrict_to_workspace=False,
            exec_timeout=60,
            brave_api_key=None,
            bus_publish_outbound=self._bus.publish_outbound,
            provider=self._provider,
            model=self._model,
            plan_manager=PlanManager(),
            origin_channel=task.origin_channel,
            origin_chat_id=task.origin_chat_id,
            thread_id=f"sub:{task.task_id}",
            execution_workspace=self._execution_workspace,
        )

    def _build_subagent_policy(self, task: Task) -> "ToolPolicyEngine":
        """构建集成 PolicyEngineV2 四维风险评估的子体策略引擎。"""
        from auraeve.subagents.control_plane.policy_v2 import PolicyEngineV2, PolicyContext as V2Context
        from auraeve.agent_runtime.tool_policy.engine import (
            ToolPolicyEngine,
            PolicyContext,
            PolicyResult,
            PolicyDecision,
        )

        v2 = PolicyEngineV2()
        base_policy = self._policy

        class SubagentPolicyEngine(ToolPolicyEngine):
            """在现有策略层上叠加 PolicyEngineV2 四维风险评估。"""

            def __init__(self, base: ToolPolicyEngine, policy_v2: PolicyEngineV2,
                         node_id: str, task_priority: int, policy_profile: str):
                super().__init__(
                    is_subagent=True,
                    global_deny=set(base._global_deny),
                    session_policy=dict(base._session_policy),
                )
                self._base = base
                self._v2 = policy_v2
                self._node_id = node_id
                self._task_priority = task_priority
                self._policy_profile = policy_profile

            async def evaluate(self, ctx: PolicyContext) -> PolicyResult:
                # 先执行基础策略
                base_result = await self._base.evaluate(ctx)
                if not base_result.allowed:
                    return base_result

                # 叠加 PolicyEngineV2 四维风险评估
                v2_ctx = V2Context(
                    tool_name=ctx.tool_name,
                    args=ctx.args,
                    node_id=self._node_id,
                    task_priority=self._task_priority,
                    policy_profile=self._policy_profile,
                )
                v2_result = self._v2.evaluate(v2_ctx)

                if v2_result.denied:
                    return PolicyResult(
                        allowed=False,
                        reason=v2_result.reason,
                        rewritten_args=base_result.rewritten_args,
                        trace=base_result.trace + [PolicyDecision(
                            layer="policy_v2",
                            rule_id="v2_denied",
                            allowed=False,
                            reason=v2_result.reason,
                        )],
                    )

                # 将风险信息附加到 trace 中供审批参考
                if v2_result.requires_approval:
                    base_result.trace.append(PolicyDecision(
                        layer="policy_v2",
                        rule_id=f"v2_risk:{v2_result.risk_level.value}",
                        allowed=True,
                        reason=f"PolicyV2: {v2_result.reason} (需审批)",
                    ))

                return base_result

        return SubagentPolicyEngine(
            base=base_policy,
            policy_v2=v2,
            node_id=task.assigned_node_id or "local",
            task_priority=task.priority,
            policy_profile=task.policy_profile,
        )

    # ── 公开 API ────────────────────────────────────────────────────────────

    async def submit_task(
        self,
        goal: str,
        priority: int = 5,
        depends_on: list[str] | None = None,
        budget: TaskBudget | None = None,
        policy_profile: str = "default",
        compensate_action: str | None = None,
        origin_channel: str = "",
        origin_chat_id: str = "",
        assigned_node_id: str = "",
        agent_name: str = "",
        role_prompt: str = "",
    ) -> Task:
        """提交单个任务。返回 Task 对象。"""
        global_running = self._db.get_running_count()
        if global_running >= self._max_global:
            raise RuntimeError(
                f"全局并发任务已达上限（{self._max_global}），当前: {global_running}"
            )

        task = Task(
            task_id=Task.new_id(),
            goal=goal,
            priority=priority,
            depends_on=depends_on or [],
            budget=budget or TaskBudget(),
            policy_profile=policy_profile,
            compensate_action=compensate_action,
            trace_id=Task.new_trace_id(),
            origin_channel=origin_channel,
            origin_chat_id=origin_chat_id,
            assigned_node_id=assigned_node_id,
            agent_name=agent_name,
            role_prompt=role_prompt,
        )
        self._db.save_task(task)
        self._telemetry.record_state_change(
            task.task_id, task.trace_id, "", "queued", "submitted",
        )
        logger.info(f"[orchestrator] 任务提交: {task.task_id} - {goal[:50]}")

        # 检查依赖，如果无依赖则立即调度
        if not task.depends_on:
            await self._dispatch_task(task)

        return task

    async def submit_dag(self, tasks: list[dict]) -> list[Task]:
        """提交 DAG 任务组。每个 dict 含 goal, depends_on 等字段。"""
        created: list[Task] = []
        id_map: dict[str, str] = {}  # 临时ID -> 实际ID

        # DAG 共享同一个 trace_id，便于追踪整个任务组
        dag_trace_id = Task.new_trace_id()

        # 第一轮：创建所有任务
        for t in tasks:
            temp_id = t.get("id", "")
            task = Task(
                task_id=Task.new_id(),
                goal=t["goal"],
                priority=t.get("priority", 5),
                depends_on=[],  # 后面填充
                budget=TaskBudget.from_dict(t["budget"]) if "budget" in t else TaskBudget(),
                policy_profile=t.get("policy_profile", "default"),
                compensate_action=t.get("compensate_action"),
                trace_id=dag_trace_id,
                origin_channel=t.get("origin_channel", ""),
                origin_chat_id=t.get("origin_chat_id", ""),
            )
            if temp_id:
                id_map[temp_id] = task.task_id
            created.append(task)

        # 第二轮：解析依赖
        for i, t in enumerate(tasks):
            raw_deps = t.get("depends_on", [])
            created[i].depends_on = [id_map.get(d, d) for d in raw_deps]

        # 保存并调度无依赖任务
        for task in created:
            self._db.save_task(task)

        for task in created:
            if not task.depends_on:
                await self._dispatch_task(task)

        return created

    async def pause_task(self, task_id: str) -> str:
        task = self._db.get_task(task_id)
        if not task:
            return f"任务 {task_id} 不存在"
        if not is_valid_transition(task.status, TaskStatus.PAUSED):
            return f"任务 {task_id} 状态 {task.status.value} 无法暂停"

        self._transition(task, TaskStatus.PAUSED, "user_pause")

        if task.assigned_node_id == "local":
            self._get_local_executor().pause(task_id)
        else:
            await self._send_remote(task.assigned_node_id, {
                "type": "task.pause", "task_id": task_id, "reason": "user_pause",
            })
        return f"任务 {task_id} 已暂停"

    async def resume_task(self, task_id: str) -> str:
        task = self._db.get_task(task_id)
        if not task:
            return f"任务 {task_id} 不存在"
        if not is_valid_transition(task.status, TaskStatus.RUNNING):
            return f"任务 {task_id} 状态 {task.status.value} 无法恢复"

        self._transition(task, TaskStatus.RUNNING, "user_resume")

        if task.assigned_node_id == "local":
            self._get_local_executor().resume(task_id)
        else:
            await self._send_remote(task.assigned_node_id, {
                "type": "task.resume", "task_id": task_id,
            })
        return f"任务 {task_id} 已恢复"

    async def cancel_task(self, task_id: str, reason: str = "user_cancel") -> str:
        task = self._db.get_task(task_id)
        if not task:
            return f"任务 {task_id} 不存在"
        if not is_valid_transition(task.status, TaskStatus.CANCELED):
            return f"任务 {task_id} 状态 {task.status.value} 无法取消"

        self._transition(task, TaskStatus.CANCELED, reason)

        if task.assigned_node_id == "local":
            self._get_local_executor().cancel(task_id)
        else:
            await self._send_remote(task.assigned_node_id, {
                "type": "task.cancel", "task_id": task_id, "reason": reason,
            })

        # DAG: 取消下游任务
        await self._cancel_downstream(task_id)

        # Saga 补偿
        if task.compensate_action:
            await self._start_compensation(task)

        return f"任务 {task_id} 已取消"

    async def steer_task(self, task_id: str, message: str) -> str:
        task = self._db.get_task(task_id)
        if not task:
            return f"任务 {task_id} 不存在"
        if task.status != TaskStatus.RUNNING:
            return f"任务 {task_id} 不在运行中"

        if task.assigned_node_id == "local":
            ok = await self._get_local_executor().steer(task_id, message)
            return "引导消息已发送" if ok else "发送失败"
        else:
            await self._send_remote(task.assigned_node_id, {
                "type": "peer.message", "task_id": task_id,
                "from_node_id": "mother", "to_node_id": task.assigned_node_id,
                "content": message,
            })
            return "引导消息已发送"

    def list_tasks(self, status: TaskStatus | None = None, limit: int = 50) -> list[Task]:
        return self._db.list_tasks(status=status, limit=limit)

    def get_task(self, task_id: str) -> Task | None:
        return self._db.get_task(task_id)

    # ── 子体上报处理（由 Reporter 调用）───────────────────────────────────

    async def handle_progress(
        self, task_id: str, step: int, message: str,
        tool_calls: int = 0, tokens_used: int = 0,
    ) -> None:
        self._telemetry.record_span(
            task_id=task_id,
            trace_id=self._get_trace_id(task_id),
            span_id=new_span_id(),
            parent_span_id="",
            operation="progress",
            node_id=self._get_node_id(task_id),
            status="ok",
            duration_ms=0,
            metadata={"step": step, "message": message[:200]},
        )

    async def handle_alert(self, task_id: str, level: str, message: str) -> None:
        logger.warning(f"[orchestrator] 告警 {task_id}: [{level}] {message}")
        self._telemetry.record_span(
            task_id=task_id,
            trace_id=self._get_trace_id(task_id),
            span_id="",
            parent_span_id="",
            operation="alert",
            node_id=self._get_node_id(task_id),
            status=level,
            duration_ms=0,
            metadata={"message": message},
        )

    async def handle_done(
        self,
        task_id: str,
        success: bool,
        result: str,
        artifacts: list[dict] | None = None,
        memory_deltas: list[dict] | None = None,
        experience: dict | None = None,
    ) -> None:
        task = self._db.get_task(task_id)
        if not task:
            return

        task.result = result
        new_status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
        self._transition(task, new_status, "done" if success else "failed")

        # 记录能力评估
        duration = time.time() - task.created_at
        domain = self._infer_domain(task.goal)
        self._tracker.record_outcome(task.assigned_node_id, domain, success, duration)

        # 保存记忆增量
        if memory_deltas:
            for md in memory_deltas:
                delta = MemoryDelta(
                    delta_id=MemoryDelta.new_id(),
                    task_id=task_id,
                    node_id=task.assigned_node_id,
                    delta_type=DeltaType(md.get("type", "observation")),
                    content=md.get("content", ""),
                    confidence=md.get("confidence", 1.0),
                )
                self._db.save_memory_delta(delta)

        if experience:
            delta = MemoryDelta(
                delta_id=MemoryDelta.new_id(),
                task_id=task_id,
                node_id=task.assigned_node_id,
                delta_type=DeltaType.EXPERIENCE,
                content=str(experience),
                confidence=experience.get("confidence", 0.8),
            )
            self._db.save_memory_delta(delta)

        # 触发记忆合并
        self._try_merge_memory()

        # 推送结果到用户渠道
        await self._deliver_result(task, result, success)

        # 补偿任务完成时，回写原任务状态为 COMPENSATED
        if success and task.goal.startswith("[补偿] "):
            self._complete_compensation(task_id)

        # DAG: 检查是否可以触发下游任务
        if success:
            await self._check_dag_ready(task_id)

        # Saga: 失败时执行补偿
        if not success and task.compensate_action:
            await self._start_compensation(task)

    async def handle_approval_request(
        self,
        task_id: str,
        approval_id: str,
        action_desc: str,
        risk_level: str,
        context: dict | None = None,
    ) -> str:
        task = self._db.get_task(task_id)
        if not task:
            return "rejected"

        self._transition(task, TaskStatus.INPUT_REQUIRED, "approval_request")

        decision = await self._approval.request_approval(
            task_id=task_id,
            approval_id=approval_id,
            action_desc=action_desc,
            risk_level=risk_level,
            context=context,
            origin_channel=task.origin_channel,
            origin_chat_id=task.origin_chat_id,
        )

        if decision in ("approve", "approved", "revise", "revised"):
            self._transition(task, TaskStatus.RUNNING, f"approval_{decision}")
        else:
            self._transition(task, TaskStatus.FAILED, f"approval_{decision}")

        return decision

    def decide_approval(self, approval_id: str, decision: str, decided_by: str = "") -> bool:
        """外部调用的审批决策入口。"""
        return self._approval.decide(approval_id, decision, decided_by)

    # ── 远程子体管理 ────────────────────────────────────────────────────────

    def register_remote_sender(self, node_id: str, sender) -> None:
        self._remote_senders[node_id] = sender

    def unregister_remote_sender(self, node_id: str) -> None:
        self._remote_senders.pop(node_id, None)

    async def on_remote_connect(self, node_id: str, msg: dict) -> list[dict]:
        """远程子体连接时调用。返回待执行任务列表。"""
        node = NodeSession(
            node_id=node_id,
            display_name=msg.get("display_name", node_id),
            platform=msg.get("platform", ""),
            capabilities=msg.get("capabilities", []),
            connected_at=time.time(),
            is_online=True,
        )
        self._db.upsert_node(node)
        logger.info(f"[orchestrator] 远程子体上线: {node_id}")

        # 恢复该节点的未完成任务
        pending = self._db.list_tasks(status=TaskStatus.DISPATCHED, node_id=node_id)
        pending += self._db.list_tasks(status=TaskStatus.RUNNING, node_id=node_id)
        return [{"task_id": t.task_id, "goal": t.goal} for t in pending]

    def on_remote_disconnect(self, node_id: str) -> None:
        self._db.set_node_online(node_id, False)
        self.unregister_remote_sender(node_id)
        logger.info(f"[orchestrator] 远程子体离线: {node_id}")

    # ── 内部方法 ────────────────────────────────────────────────────────────

    async def _dispatch_task(self, task: Task) -> None:
        """调度任务到最优子体。"""
        if task.assigned_node_id:
            node_id = task.assigned_node_id
        else:
            node_id = self._scheduler.select_node(task)
            if not node_id:
                logger.warning(f"[orchestrator] 任务 {task.task_id} 无可用子体")
                return

        self._db.assign_task(task.task_id, node_id)
        task.assigned_node_id = node_id
        task.status = TaskStatus.DISPATCHED

        self._telemetry.record_state_change(
            task.task_id, task.trace_id, "queued", "dispatched", f"assigned to {node_id}",
        )

        if node_id == "local":
            self._transition(task, TaskStatus.RUNNING, "local_start")
            await self._get_local_executor().execute(task)
        else:
            await self._send_remote(node_id, {
                "type": "task.assign",
                "task_id": task.task_id,
                "goal": task.goal,
                "budget": task.budget.to_dict(),
                "policy_profile": task.policy_profile,
                "trace": {"trace_id": task.trace_id},
            })
            self._transition(task, TaskStatus.RUNNING, "remote_start")

    def _transition(self, task: Task, new_status: TaskStatus, reason: str) -> None:
        old = task.status
        if not is_valid_transition(old, new_status):
            logger.warning(
                f"[orchestrator] 非法状态迁移: {task.task_id} {old.value} -> {new_status.value}"
            )
            return
        self._db.update_task_status(task.task_id, new_status)
        task.status = new_status
        self._telemetry.record_state_change(
            task.task_id, task.trace_id, old.value, new_status.value, reason,
        )

    async def _send_remote(self, node_id: str, msg: dict) -> None:
        sender = self._remote_senders.get(node_id)
        if sender:
            import json
            await sender(json.dumps(msg, ensure_ascii=False))
        else:
            logger.warning(f"[orchestrator] 远程子体 {node_id} 不在线，无法发送")

    async def _check_dag_ready(self, completed_task_id: str) -> None:
        """检查依赖 completed_task_id 的任务是否可以开始。"""
        all_tasks = self._db.list_tasks(status=TaskStatus.QUEUED, limit=200)
        for t in all_tasks:
            if completed_task_id in t.depends_on:
                deps_met = all(
                    (dt := self._db.get_task(d)) and dt.status == TaskStatus.COMPLETED
                    for d in t.depends_on
                )
                if deps_met:
                    await self._dispatch_task(t)

    async def _cancel_downstream(self, failed_task_id: str) -> None:
        all_tasks = self._db.list_tasks(limit=200)
        for t in all_tasks:
            if failed_task_id in t.depends_on and t.status == TaskStatus.QUEUED:
                self._transition(t, TaskStatus.CANCELED, f"upstream {failed_task_id} failed")

    async def _start_compensation(self, task: Task) -> None:
        if not task.compensate_action:
            return
        if is_valid_transition(task.status, TaskStatus.COMPENSATING):
            self._transition(task, TaskStatus.COMPENSATING, "start_compensation")
            try:
                comp_task = await self.submit_task(
                    goal=f"[补偿] {task.compensate_action}",
                    priority=task.priority,
                    origin_channel=task.origin_channel,
                    origin_chat_id=task.origin_chat_id,
                    assigned_node_id=task.assigned_node_id,
                )
                # 记录补偿任务与原任务的关联
                self._compensation_map[comp_task.task_id] = task.task_id
                logger.info(f"[orchestrator] 补偿任务已创建: {comp_task.task_id} (原任务: {task.task_id})")
            except Exception as e:
                logger.error(f"[orchestrator] 补偿任务创建失败: {e}")

    async def _deliver_result(self, task: Task, result: str, success: bool) -> None:
        """将子体结果注入母体对话上下文，由母体 LLM 决定如何回复用户。"""
        if not task.origin_channel:
            return

        # 构建兄弟任务状态摘要，注入 runtime_instruction 供母体判断是否等待其他子体
        sibling_context: str | None = None
        if task.trace_id:
            siblings = self._db.list_tasks_by_trace(task.trace_id)
            if len(siblings) > 1:
                other = [t for t in siblings if t.task_id != task.task_id]
                still_running = [
                    t for t in other
                    if t.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELED)
                ]
                if still_running:
                    names = "、".join(
                        f"{t.task_id[:8]}({t.goal[:20]})" for t in still_running
                    )
                    sibling_context = (
                        f"同批次还有 {len(still_running)} 个子体任务尚未完成：{names}。"
                        "如果你认为需要等它们的结果再给用户完整答复，可以先告知用户正在等待其他子体，"
                        "它们完成后会再次触发你；也可以用已有信息先部分回复，再补充后续结果。"
                    )
                else:
                    sibling_context = f"同批次所有 {len(siblings)} 个子体任务已全部完成。"

        await self._inject_result_to_mother(task, result, success, sibling_context=sibling_context)

    async def _inject_result_to_mother(
        self, task: Task, result: str, success: bool, raw: bool = False,
        sibling_context: str | None = None,
    ) -> None:
        """将子体结果注入母体上下文，作为 synthetic tool result 触发续写。"""
        if not task.origin_channel or not task.origin_chat_id:
            return

        session_key = f"{task.origin_channel}:{task.origin_chat_id}"
        if session_key not in self._session_locks:
            self._session_locks[session_key] = asyncio.Lock()

        async with self._session_locks[session_key]:
            if task.task_id in self._injected_task_ids:
                return
            self._injected_task_ids.add(task.task_id)

            if not self._kernel_resume_callback:
                logger.warning("[orchestrator] kernel_resume_callback 未注册，跳过结果注入")
                return

            tool_call_id = task.spawn_tool_call_id or f"call_subagent_{uuid.uuid4().hex[:8]}"
            icon = "success" if success else "failed"
            summary = result[:500]
            final_answer = result if raw else result[:3000]
            error = None if success else summary

            result_payload = {
                "status": icon,
                "source": "async_subagent_callback",
                "agent_name": task.agent_name or "subagent",
                "task_id": task.task_id,
                "summary": summary,
                "final_answer": final_answer,
                "key_findings": [],
                "confidence": 1.0 if success else 0.0,
                "needs_more_work": not success,
                "artifacts": [],
                "error": error,
            }

            synthetic_messages = [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": "subagent_result",
                            "arguments": json.dumps({
                                "task_id": task.task_id,
                                "agent_name": task.agent_name or "subagent",
                                "goal": task.goal,
                                "requested_by": "mother_agent",
                                "result_mode": "async_callback",
                            }, ensure_ascii=False),
                        },
                    }],
                },
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": "subagent_result",
                    "content": json.dumps(result_payload, ensure_ascii=False),
                },
            ]

            runtime_instruction = (
                "当前上下文中存在由系统补注入的 subagent_result tool_use/tool_result，"
                "这是异步子体任务完成后的回调结果，应视为已完成的工具调用直接消费，无需质疑其来源。"
                "若此前已告知用户正在处理中，本次应优先直接给出结果，不重复过程性提示。"
            )
            if sibling_context:
                runtime_instruction += f"\n[子体批次状态] {sibling_context}"

        try:
            outbound = await self._kernel_resume_callback(
                session_key=session_key,
                channel=task.origin_channel,
                chat_id=task.origin_chat_id,
                synthetic_messages=synthetic_messages,
                runtime_instruction=runtime_instruction,
            )
            if outbound:
                await self._bus.publish_outbound(outbound)
        except Exception as e:
            logger.error(f"[orchestrator] 结果注入母体失败: {e}")

    def _get_trace_id(self, task_id: str) -> str:
        task = self._db.get_task(task_id)
        return task.trace_id if task else ""

    def _get_node_id(self, task_id: str) -> str:
        task = self._db.get_task(task_id)
        return task.assigned_node_id if task else ""

    def _infer_domain(self, goal: str) -> str:
        goal_lower = goal.lower()
        if any(k in goal_lower for k in ("shell", "命令", "执行", "运行")):
            return "shell"
        if any(k in goal_lower for k in ("文件", "读取", "写入")):
            return "file_ops"
        if any(k in goal_lower for k in ("搜索", "网页", "api")):
            return "web"
        return "general"

    def _complete_compensation(self, comp_task_id: str) -> None:
        """补偿任务完成后，将原任务状态迁移到 COMPENSATED。"""
        original_task_id = self._compensation_map.pop(comp_task_id, None)
        if not original_task_id:
            return
        original_task = self._db.get_task(original_task_id)
        if original_task and is_valid_transition(original_task.status, TaskStatus.COMPENSATED):
            self._transition(original_task, TaskStatus.COMPENSATED, "compensation_done")
            logger.info(f"[orchestrator] 原任务 {original_task_id} 已补偿完成")

    def _try_merge_memory(self) -> None:
        """尝试触发记忆增量合并到母体知识图谱。"""
        try:
            if self._merge_service is None:
                from auraeve.subagents.memory.merge_service import MemoryMergeService
                from auraeve.subagents.data.graph_store import GraphStore
                graph_path = self._workspace / "data" / "knowledge_graph.db"
                graph_path.parent.mkdir(parents=True, exist_ok=True)
                graph = GraphStore(graph_path)
                self._merge_service = MemoryMergeService(self._db, graph)
            self._merge_service.merge_pending(batch_size=20)
        except Exception as e:
            logger.error(f"[orchestrator] 记忆合并失败: {e}")

    def format_task_summary(self, task: Task) -> str:
        icon = STATUS_ICON.get(task.status, "❓")
        elapsed = round(time.time() - task.created_at, 1)
        node = task.assigned_node_id or "未分配"
        return f"{icon} [{task.task_id}] {task.goal[:40]}（{task.status.value}, {node}, {elapsed}s）"
