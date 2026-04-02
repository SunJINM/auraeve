"""子智能体执行器。

合并了原来的 TaskOrchestrator + LocalSubAgentExecutor 的核心逻辑。
去掉了 DAG/审批/远程调度/能力评分/遥测/记忆合并。

职责:
- 创建任务并持久化
- 本地异步执行（asyncio.Task）
- 并发控制
- 完成后发送通知
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

from .context_isolation import generate_agent_id
from .data.models import Task, TaskBudget, TaskStatus
from .data.repositories import SubagentStore
from .notification import NotificationQueue, TaskNotification
from .runtime.react_loop import ReActLoop
from .runtime.reporter import TaskReporter

logger = logging.getLogger(__name__)


class _InProcessReporter(TaskReporter):
    """进程内上报器。"""

    def __init__(self, store: SubagentStore) -> None:
        self._store = store

    async def report_progress(
        self,
        task_id: str,
        step: int,
        message: str,
        tool_calls: int = 0,
        tokens_used: int = 0,
    ) -> None:
        logger.debug("子智能体进度 %s: step=%d %s", task_id, step, message)

    async def report_done(
        self,
        task_id: str,
        success: bool,
        result: str,
    ) -> None:
        logger.info("子智能体完成 %s: success=%s", task_id, success)


class SubagentExecutor:
    """子智能体执行器。"""

    def __init__(
        self,
        *,
        store: SubagentStore,
        notification_queue: NotificationQueue,
        provider,
        tool_builder: Callable,
        policy,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        max_iterations: int = 200,
        thinking_budget_tokens: int = 0,
        max_concurrent: int = 5,
        workspace: str = "",
        kernel_resume_callback: Callable | None = None,
    ) -> None:
        self._store = store
        self._notification_queue = notification_queue
        self._provider = provider
        self._tool_builder = tool_builder
        self._policy = policy
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_iterations = max_iterations
        self._thinking_budget_tokens = thinking_budget_tokens
        self._max_concurrent = max_concurrent
        self._workspace = workspace
        self._kernel_resume_callback = kernel_resume_callback

        self._running: dict[str, asyncio.Task] = {}
        self._loops: dict[str, ReActLoop] = {}
        self._injected_ids: set[str] = set()
        self._inject_lock = asyncio.Lock()

    # ── 任务管理 ──────────────────────────────────────────

    def create_task(
        self,
        goal: str,
        agent_type: str = "general-purpose",
        origin_channel: str = "",
        origin_chat_id: str = "",
        spawn_tool_call_id: str = "",
        priority: int = 5,
        role_prompt: str = "",
        budget: TaskBudget | None = None,
        run_in_background: bool = True,
    ) -> Task:
        """创建子智能体任务。"""
        if len(self._running) >= self._max_concurrent:
            raise RuntimeError(
                f"子智能体并发数已达上限（{self._max_concurrent}），请等待现有任务完成"
            )

        task = Task(
            task_id=generate_agent_id(),
            goal=goal,
            agent_type=agent_type,
            priority=priority,
            budget=budget or TaskBudget(),
            role_prompt=role_prompt,
            origin_channel=origin_channel,
            origin_chat_id=origin_chat_id,
            spawn_tool_call_id=spawn_tool_call_id,
            run_in_background=run_in_background,
        )
        self._store.save_task(task)
        return task

    def list_tasks(self, status: TaskStatus | None = None, limit: int = 50) -> list[Task]:
        return self._store.list_tasks(status=status, limit=limit)

    def get_task(self, task_id: str) -> Task | None:
        return self._store.get_task(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """取消任务。"""
        task = self._store.get_task(task_id)
        if task is None:
            return False

        if task.task_id in self._loops:
            self._loops[task.task_id].cancel()

        if task.task_id in self._running:
            self._running[task.task_id].cancel()
            del self._running[task.task_id]

        self._store.update_task_status(task_id, TaskStatus.KILLED)
        return True

    # ── 执行 ──────────────────────────────────────────────

    async def execute_async(self, task: Task) -> None:
        """异步执行子智能体任务（后台 asyncio.Task）。"""
        async_task = asyncio.create_task(self._run_lifecycle(task))
        self._running[task.task_id] = async_task

    async def execute_sync(self, task: Task) -> str:
        """同步执行子智能体任务（等待结果返回）。"""
        return await self._run_task(task)

    async def _run_lifecycle(self, task: Task) -> None:
        """异步生命周期：执行 → 完成通知 → 结果注入。"""
        try:
            result = await self._run_task(task)
            self._store.complete_task(
                task.task_id, result=result, completed_at=time.time()
            )
            notification = TaskNotification(
                task_id=task.task_id,
                agent_type=task.agent_type,
                goal=task.goal,
                status="completed",
                result=result,
                spawn_tool_call_id=task.spawn_tool_call_id,
            )
            self._notification_queue.enqueue(notification)
            await self._try_inject_result(task, notification)

        except asyncio.CancelledError:
            self._store.update_task_status(task.task_id, TaskStatus.KILLED)
            self._notification_queue.enqueue(TaskNotification(
                task_id=task.task_id, agent_type=task.agent_type,
                goal=task.goal, status="killed", result="任务被取消",
                spawn_tool_call_id=task.spawn_tool_call_id,
            ))

        except Exception as e:
            logger.exception("子智能体执行失败: %s", task.task_id)
            error_msg = str(e)
            self._store.update_task_status(task.task_id, TaskStatus.FAILED)
            notification = TaskNotification(
                task_id=task.task_id, agent_type=task.agent_type,
                goal=task.goal, status="failed", result=error_msg,
                spawn_tool_call_id=task.spawn_tool_call_id,
            )
            self._notification_queue.enqueue(notification)
            await self._try_inject_result(task, notification)

        finally:
            self._running.pop(task.task_id, None)
            self._loops.pop(task.task_id, None)

    async def _run_task(self, task: Task) -> str:
        """执行子智能体 ReAct 循环。"""
        self._store.update_task_status(task.task_id, TaskStatus.RUNNING)

        reporter = _InProcessReporter(self._store)
        tools = self._tool_builder(task)

        loop = ReActLoop(
            provider=self._provider,
            tools=tools,
            policy=self._policy,
            model=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            max_iterations=self._max_iterations,
            thinking_budget_tokens=self._thinking_budget_tokens,
            reporter=reporter,
        )
        self._loops[task.task_id] = loop

        return await loop.run(task)

    async def _try_inject_result(
        self, task: Task, notification: TaskNotification
    ) -> None:
        """尝试将子智能体结果注入母体上下文。"""
        if not self._kernel_resume_callback:
            return
        if not task.spawn_tool_call_id:
            return

        async with self._inject_lock:
            if task.task_id in self._injected_ids:
                return
            self._injected_ids.add(task.task_id)

        synthetic = self._notification_queue.build_synthetic_messages(notification)
        try:
            await self._kernel_resume_callback(
                channel=task.origin_channel,
                chat_id=task.origin_chat_id,
                synthetic_messages=synthetic,
            )
        except Exception:
            logger.exception("注入子智能体结果到母体失败: %s", task.task_id)
