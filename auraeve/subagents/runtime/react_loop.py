"""子智能体 ReAct 执行循环。

简化版：去掉审批、能力注册、经验提取、本地记忆。
保留核心的 LLM 工具循环 + 进度上报 + 超时/取消处理。
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from auraeve.agent.agents.definitions import find_agent
from auraeve.subagents.data.models import Task, ProgressTracker
from .reporter import TaskReporter

logger = logging.getLogger(__name__)


class ReActLoop:
    """子智能体 ReAct 执行循环。"""

    def __init__(
        self,
        *,
        provider,
        tools,
        policy,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        max_iterations: int = 200,
        thinking_budget_tokens: int = 0,
        reporter: TaskReporter | None = None,
    ) -> None:
        self._provider = provider
        self._tools = tools
        self._policy = policy
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_iterations = max_iterations
        self._thinking_budget_tokens = thinking_budget_tokens
        self._reporter = reporter
        self._task: asyncio.Task | None = None
        self.progress = ProgressTracker()
        self.messages: list[dict] = []

    async def run(
        self,
        task: Task,
        history_messages: list[dict] | None = None,
        steer_queue: asyncio.Queue | None = None,
    ) -> str:
        """执行完整的 ReAct 循环。"""
        from auraeve.agent_runtime.session_attempt import SessionAttemptRunner
        from auraeve.agent_runtime.run_orchestrator import RunOrchestrator
        from auraeve.plugins import PluginRegistry

        system_prompt = self._build_system_prompt(task)

        effective_max_steps = min(self._max_iterations, task.budget.max_steps)
        max_tc = task.budget.max_tool_calls
        per_turn = max(4, max_tc // 4)
        runtime_execution = {
            "maxTurns": effective_max_steps,
            "maxToolCallsTotal": max_tc,
            "maxToolCallsPerTurn": per_turn,
        }

        hooks = PluginRegistry().build_hook_runner()

        runner = SessionAttemptRunner(
            provider=self._provider,
            tools=self._tools,
            policy=self._policy,
            hooks=hooks,
            max_iterations=effective_max_steps,
            thinking_budget_tokens=self._thinking_budget_tokens,
            runtime_execution=runtime_execution,
        )

        orchestrator = RunOrchestrator(
            runner=runner,
            provider=self._provider,
            max_retries=5,
            is_subagent=True,
        )

        messages = self._prepare_messages(task, history_messages or [])

        start_time = time.monotonic()

        try:
            timeout = task.budget.max_duration_s if task.budget.max_duration_s > 0 else None
            coro = orchestrator.run(
                messages=messages,
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                thread_id=f"sub:{task.task_id}",
                steer_queue=steer_queue,
            )
            if timeout:
                result = await asyncio.wait_for(coro, timeout=timeout)
            else:
                result = await coro

            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            self.progress.duration_ms = elapsed_ms
            final_content = result.final_content or ""
            self.messages = list(result.messages or [])

            if self._reporter:
                await self._reporter.report_done(
                    task_id=task.task_id,
                    success=True,
                    result=final_content,
                )

            return final_content

        except asyncio.TimeoutError:
            logger.warning("子智能体超时: %s (budget=%ds)", task.task_id, task.budget.max_duration_s)
            if self._reporter:
                await self._reporter.report_done(
                    task_id=task.task_id,
                    success=False,
                    result=f"执行超时（{task.budget.max_duration_s}秒）",
                )
            raise

        except asyncio.CancelledError:
            logger.info("子智能体被取消: %s", task.task_id)
            if self._reporter:
                await self._reporter.report_done(
                    task_id=task.task_id,
                    success=False,
                    result="任务被取消",
                )
            raise

    def cancel(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    def _build_system_prompt(self, task: Task) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        agent_def = find_agent(task.agent_type)
        parts = [
            f"当前时间: {now}",
            "",
            "你正在作为子智能体执行任务。",
            f"子智能体类型: {task.agent_type}",
            f"执行模式: {task.execution_mode}",
            f"上下文模式: {task.context_mode}",
            f"执行预算: 最多 {task.budget.max_steps} 步, "
            f"最多 {task.budget.max_tool_calls} 次工具调用, "
            f"最长 {task.budget.max_duration_s} 秒。",
            "",
            "角色说明:",
            agent_def.system_prompt or "按分配目标完成任务。",
            "",
            "执行约束:",
            "- 专注于你的任务目标，不要偏离",
            "- 高效使用工具，避免重复操作",
            "- 通过工具调用显著提升结论质量；每次调用都应扩大信息增量、减少不确定性，并推动下一步判断",
            "- 积极组合使用 Read、Grep、Glob、Bash 和其他可用工具，而不是停留在单一视角",
            "- 只有彼此独立、互不依赖的只读工具调用，才应并发发出",
            "- 依赖前一步结果的调用必须串行执行",
            "- 完成后输出清晰、结构化的结果",
            "- 如果发现任务无法完成，说明原因并返回已有成果",
        ]

        if task.role_prompt:
            parts.extend(["", "角色配置:", task.role_prompt])

        return "\n".join(parts)

    def _prepare_messages(
        self,
        task: Task,
        history_messages: list[dict] | None = None,
    ) -> list[dict]:
        messages: list[dict] = [
            {"role": "system", "content": self._build_system_prompt(task)},
        ]
        if history_messages:
            messages.extend(history_messages)
        messages.append({"role": "user", "content": task.goal})
        return messages
