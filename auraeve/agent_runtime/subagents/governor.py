"""SubagentGovernor：子代理并发治理 + 全生命周期管理。

替代原 SubagentManager，对外保持相同接口（spawn/steer/kill/list_tasks）。
内部使用 SessionAttemptRunner + RunOrchestrator，
与主代理共享同一执行内核。

并发控制：
  max_global_concurrent  → 全局最大并发子代理数
  max_session_concurrent → 单会话最大并发子代理数
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from loguru import logger

from auraeve.agent.context import ContextBuilder
from auraeve.agent.tools.assembler import build_tool_registry

from .registry import SubagentRegistry, SubagentRecord, SubagentStatus

if TYPE_CHECKING:
    from auraeve.providers.base import LLMProvider
    from auraeve.bus.queue import MessageBus
    from auraeve.plugins.hooks import HookRunner
    from auraeve.agent_runtime.tool_policy.engine import ToolPolicyEngine


class SubagentGovernor:
    """
    子代理治理器。

    参数：
        registry:              SubagentRegistry 实例
        provider:              LLMProvider
        workspace:             工作区路径
        bus:                   MessageBus（用于推送结果到渠道）
        model:                 默认模型
        temperature / max_tokens / max_iterations：执行参数
        brave_api_key / exec_timeout / restrict_to_workspace：工具参数
        thinking_budget_tokens：推理 token 预算
        policy:                ToolPolicyEngine（子代理模式）
        hooks:                 HookRunner
        max_global_concurrent: 全局并发上限
        max_session_concurrent:单会话并发上限
    """

    def __init__(
        self,
        registry: SubagentRegistry,
        provider: "LLMProvider",
        workspace: Path,
        bus: "MessageBus",
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        max_iterations: int = 50,
        brave_api_key: str | None = None,
        exec_timeout: int = 60,
        restrict_to_workspace: bool = False,
        thinking_budget_tokens: int | None = None,
        policy: "ToolPolicyEngine | None" = None,
        hooks: "HookRunner | None" = None,
        max_global_concurrent: int = 10,
        max_session_concurrent: int = 3,
        execution_workspace: str | None = None,
    ) -> None:
        self._registry = registry
        self._provider = provider
        self._workspace = workspace
        self._bus = bus
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_iterations = max_iterations
        self._brave_api_key = brave_api_key
        self._exec_timeout = exec_timeout
        self._restrict_to_workspace = restrict_to_workspace
        self._thinking_budget_tokens = thinking_budget_tokens
        self._policy = policy
        self._hooks = hooks
        self._max_global = max_global_concurrent
        self._max_session = max_session_concurrent
        self._execution_workspace = execution_workspace

        # 运行中任务的 asyncio.Task + steer 队列
        self._asyncio_tasks: dict[str, asyncio.Task] = {}
        self._steer_queues: dict[str, asyncio.Queue] = {}

        # 子代理专用 MemoryStore（记忆上下文注入）
        from auraeve.agent.memory import MemoryStore
        from auraeve.agent.plan import PlanManager
        self._memory = MemoryStore(workspace)
        self._plan = PlanManager()
        self._context_builder = ContextBuilder(
            workspace,
            execution_workspace=execution_workspace,
        )

    # ── 公开接口（与 SubagentManager 相同）──────────────────────────────────

    async def spawn(
        self,
        task: str,
        label: str | None = None,
        origin_channel: str = "dingtalk",
        origin_chat_id: str = "direct",
    ) -> str:
        """派生后台子代理，立即返回任务 ID。"""
        # 并发配额检查
        session_key = f"{origin_channel}:{origin_chat_id}"
        global_running = self._registry.get_running_count()
        session_running = self._registry.get_running_count(session_key)

        if global_running >= self._max_global:
            return (
                f"子代理并发已达全局上限（{self._max_global}），请等待任务完成后再派生。"
                f"当前运行中：{global_running}"
            )
        if session_running >= self._max_session:
            return (
                f"当前会话并发已达上限（{self._max_session}），请等待任务完成后再派生。"
                f"当前运行中：{session_running}"
            )

        task_id = str(uuid.uuid4())[:8]
        display_label = label or (task[:30] + ("…" if len(task) > 30 else ""))

        record = SubagentRecord(
            id=task_id,
            label=display_label,
            task=task,
            status=SubagentStatus.CREATED,
            started_at=time.time(),
            origin_channel=origin_channel,
            origin_chat_id=origin_chat_id,
        )
        self._registry.register(record)
        self._registry.update_status(task_id, SubagentStatus.RUNNING, reason="spawn")
        self._steer_queues[task_id] = asyncio.Queue()

        bg_task = asyncio.create_task(
            self._run_subagent(task_id, task, display_label, origin_channel, origin_chat_id)
        )
        self._asyncio_tasks[task_id] = bg_task
        bg_task.add_done_callback(lambda _: self._cleanup(task_id))

        logger.info(f"[governor] 派生子代理 [{task_id}]：{display_label}")
        return f"子代理 [{display_label}] 已启动（id: {task_id}），完成后将直接通知用户。"

    async def steer(self, task_id: str, message: str) -> str:
        """向运行中的子代理推送引导消息。"""
        record = self._registry.get(task_id)
        if not record:
            return f"任务 {task_id} 不存在"
        if record.status != SubagentStatus.RUNNING:
            return f"任务 {task_id} 已处于 {record.status.value} 状态，无法引导"
        queue = self._steer_queues.get(task_id)
        if not queue:
            return f"任务 {task_id} 的引导队列不可用"
        await queue.put(message)
        logger.info(f"[governor] 向 [{task_id}] 发送引导：{message[:80]}")
        return f"引导消息已发送给子代理 [{task_id}]（{record.label}）"

    async def kill(self, task_id: str) -> str:
        """中止正在运行的子代理。"""
        record = self._registry.get(task_id)
        if not record:
            return f"任务 {task_id} 不存在"
        if record.status != SubagentStatus.RUNNING:
            return f"任务 {task_id} 已处于 {record.status.value} 状态，无需中止"
        bg_task = self._asyncio_tasks.get(task_id)
        if bg_task and not bg_task.done():
            bg_task.cancel()
        self._registry.update_status(
            task_id, SubagentStatus.CANCELLED,
            finished_at=time.time(), reason="kill"
        )
        logger.info(f"[governor] 子代理 [{task_id}] 已被主动中止")
        return f"子代理 [{task_id}]（{record.label}）已中止"

    # 保留旧名称兼容
    async def cancel(self, task_id: str) -> str:
        return await self.kill(task_id)

    def list_tasks(self, recent_minutes: float | None = None) -> list[SubagentRecord]:
        return self._registry.list_tasks(recent_minutes=recent_minutes)

    def get_running_count(self) -> int:
        return self._registry.get_running_count()

    # ── 内部执行 ─────────────────────────────────────────────────────────────

    def _cleanup(self, task_id: str) -> None:
        self._asyncio_tasks.pop(task_id, None)
        self._steer_queues.pop(task_id, None)

    async def _run_subagent(
        self,
        task_id: str,
        task: str,
        label: str,
        origin_channel: str,
        origin_chat_id: str,
    ) -> None:
        thread_id = f"sub:{task_id}"
        logger.info(f"[governor] 子代理 [{task_id}] 开始执行：{label}")

        try:
            from auraeve.agent_runtime.tool_policy.engine import ToolPolicyEngine
            from auraeve.agent_runtime.session_attempt import SessionAttemptRunner
            from auraeve.agent_runtime.run_orchestrator import RunOrchestrator
            from auraeve.plugins import PluginRegistry

            # 子代理专用工具集（不含 spawn）
            tools = self._build_tools(origin_channel, origin_chat_id, thread_id)

            # 子代理策略引擎（is_subagent=True）
            sub_policy = self._policy or ToolPolicyEngine(is_subagent=True)
            if not sub_policy._is_subagent:
                sub_policy = ToolPolicyEngine(
                    is_subagent=True,
                    global_deny=set(sub_policy._global_deny),
                    session_policy=dict(sub_policy._session_policy),
                )

            # 子代理 hooks（复用主代理 hooks 或空 runner）
            hooks = self._hooks
            if hooks is None:
                hooks = PluginRegistry().build_hook_runner()

            runner = SessionAttemptRunner(
                provider=self._provider,
                tools=tools,
                policy=sub_policy,
                hooks=hooks,
                max_iterations=self._max_iterations,
                thinking_budget_tokens=self._thinking_budget_tokens,
            )
            orchestrator = RunOrchestrator(
                runner=runner,
                provider=self._provider,
                max_retries=5,
                is_subagent=True,
            )

            # 构建初始消息
            initial_messages = [
                {"role": "system", "content": self._build_system_prompt(thread_id)},
                {"role": "user", "content": task},
            ]

            steer_queue = self._steer_queues.get(task_id, asyncio.Queue())
            result = await orchestrator.run(
                messages=initial_messages,
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                thread_id=thread_id,
                channel=origin_channel,
                chat_id=origin_chat_id,
                steer_queue=steer_queue,
            )

            final_content = result.final_content or "任务已完成，未生成文字结论。"
            self._registry.update_status(
                task_id, SubagentStatus.COMPLETED,
                finished_at=time.time(), reason="done"
            )
            record = self._registry.get(task_id)
            elapsed = record.elapsed() if record else 0
            logger.info(f"[governor] 子代理 [{task_id}] 完成（{elapsed}s）")
            await self._deliver_result(task_id, label, final_content, origin_channel, origin_chat_id, "ok")

        except asyncio.CancelledError:
            # kill() 已更新状态，此处仅记录日志
            logger.info(f"[governor] 子代理 [{task_id}] 被取消")

        except Exception as e:
            self._registry.update_status(
                task_id, SubagentStatus.FAILED,
                finished_at=time.time(),
                error_reason=str(e),
                reason="exception",
            )
            logger.error(f"[governor] 子代理 [{task_id}] 执行失败：{e}")
            await self._deliver_result(
                task_id, label, f"执行出错：{e}", origin_channel, origin_chat_id, "error"
            )

        finally:
            self._plan.clear_plan(f"sub:{task_id}")

    def _build_tools(
        self,
        origin_channel: str,
        origin_chat_id: str,
        thread_id: str,
    ):
        return build_tool_registry(
            profile="subagent",
            workspace=self._workspace,
            restrict_to_workspace=self._restrict_to_workspace,
            exec_timeout=self._exec_timeout,
            brave_api_key=self._brave_api_key,
            bus_publish_outbound=self._bus.publish_outbound,
            provider=self._provider,
            model=self._model,
            plan_manager=self._plan,
            origin_channel=origin_channel,
            origin_chat_id=origin_chat_id,
            thread_id=thread_id,
            execution_workspace=self._execution_workspace,
        )

    def _build_system_prompt(self, thread_id: str) -> str:
        tz_name = os.getenv("AURAEVE_TIMEZONE") or os.getenv("TZ") or "Asia/Shanghai"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz_name = "Asia/Shanghai"
            tz = ZoneInfo(tz_name)
        now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
        memory_ctx = self._memory.get_memory_context()
        memory_section = f"\n\n## 长期记忆\n{memory_ctx}" if memory_ctx else ""
        plan_fragment = self._plan.format_for_prompt(thread_id)
        plan_section = f"\n\n---\n\n{plan_fragment}" if plan_fragment else ""

        base_prompt = self._context_builder.build_system_prompt(
            channel="subagent",
            chat_id=thread_id,
            available_tools={
                "read_file", "write_file", "edit_file", "list_dir",
                "exec", "web_search", "web_fetch", "message", "todo",
            },
            prompt_mode="minimal",
        )

        subagent_section = (
            "## 子代理执行约束\n"
            "你是被派生的后台子代理，只负责当前任务。\n"
            "复杂任务先用 todo 建立计划，并持续更新状态。\n"
            "若收到 [引导消息]，立即调整执行方向。\n"
            "完成后给出清晰结论，不要求用户二次确认。"
        )

        workspace_section = f"## 工作区\n{self._workspace}\n\n"
        if self._execution_workspace:
            workspace_section += f"## 命令执行目录\n{self._execution_workspace}\n\n"

        return (
            f"{base_prompt}\n\n---\n\n"
            f"# 子代理\n\n"
            f"## 当前时间\n{now} ({tz_name})\n\n"
            f"{workspace_section}"
            f"{subagent_section}"
            f"{memory_section}{plan_section}"
        )

    async def _deliver_result(
        self,
        task_id: str,
        label: str,
        result: str,
        origin_channel: str,
        origin_chat_id: str,
        status: str,
    ) -> None:
        from auraeve.bus.events import OutboundMessage
        icon = "✅" if status == "ok" else "❌"
        content = f"{icon} **后台任务完成：{label}**\n\n{result}"
        try:
            await self._bus.publish_outbound(OutboundMessage(
                channel=origin_channel,
                chat_id=origin_chat_id,
                content=content,
            ))
        except Exception as e:
            logger.error(f"[governor] 子代理 [{task_id}] 结果推送失败：{e}")
