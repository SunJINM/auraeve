"""子智能体执行器。

职责:
- 创建任务并持久化
- 本地异步执行（asyncio.Task）
- 并发控制
- 将生命周期事件委托给 SubagentLifecycle
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.agent.agents.definitions import find_agent
from auraeve.session.manager import SessionManager

from .context_isolation import generate_agent_id
from .data.models import Task, TaskBudget, TaskStatus
from .data.repositories import SubagentStore
from .lifecycle import SubagentLifecycle
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
        command_queue: RuntimeCommandQueue,
        provider,
        tool_builder,
        policy,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        max_iterations: int = 200,
        thinking_budget_tokens: int = 0,
        max_concurrent: int = 5,
        workspace: str = "",
        sessions_dir: str | Path | None = None,
    ) -> None:
        self._store = store
        self._command_queue = command_queue
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
        self._sessions = SessionManager(Path(sessions_dir) if sessions_dir else Path(workspace) / ".subagents")
        self._lifecycle = SubagentLifecycle(
            store=store,
            command_queue=command_queue,
        )

        self._running: dict[str, asyncio.Task] = {}
        self._loops: dict[str, ReActLoop] = {}
        self._steer_queues: dict[str, asyncio.Queue[str]] = {}

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
        run_in_background: bool | None = None,
        execution_mode: str = "sync",
        context_mode: str = "fresh",
        name: str = "",
        description: str = "",
        session_key: str = "",
        parent_thread_id: str = "",
        parent_task_id: str = "",
        seed_messages: list[dict] | None = None,
    ) -> Task:
        """创建子智能体任务。"""
        if len(self._running) >= self._max_concurrent:
            raise RuntimeError(
                f"子智能体并发数已达上限（{self._max_concurrent}），请等待现有任务完成"
            )

        execution_mode = (execution_mode or "sync").strip().lower()
        if execution_mode not in {"sync", "async", "fork"}:
            execution_mode = "sync"
        if execution_mode == "fork":
            context_mode = "inherit"
        context_mode = (context_mode or "fresh").strip().lower()
        if context_mode not in {"fresh", "inherit"}:
            context_mode = "fresh"
        if run_in_background is None:
            run_in_background = execution_mode in {"async", "fork"}

        task_id = generate_agent_id()
        task = Task(
            task_id=task_id,
            goal=goal,
            agent_type=agent_type,
            priority=priority,
            budget=budget or TaskBudget(),
            name=name,
            description=description,
            role_prompt=role_prompt,
            origin_channel=origin_channel,
            origin_chat_id=origin_chat_id,
            spawn_tool_call_id=spawn_tool_call_id,
            execution_mode=execution_mode,
            context_mode=context_mode,
            run_in_background=run_in_background,
            session_key=session_key or f"sub:{task_id}",
            parent_thread_id=parent_thread_id,
            parent_task_id=parent_task_id,
            seed_messages_json=json.dumps(seed_messages or [], ensure_ascii=False),
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
        steer_queue = self._new_steer_queue()
        self._steer_queues[task.task_id] = steer_queue
        async_task = asyncio.create_task(self._run_lifecycle(task, steer_queue))
        self._running[task.task_id] = async_task

    async def execute_sync(self, task: Task) -> str:
        """同步执行子智能体任务（等待结果返回）。"""
        return await self._run_task(task, self._new_steer_queue())

    async def continue_task(
        self,
        task_id: str,
        prompt: str,
        *,
        execution_mode: str | None = None,
    ) -> str:
        task = self._store.get_task(task_id)
        if task is None:
            return f"未找到任务: {task_id}"

        if task_id in self._running and task_id in self._steer_queues:
            await self._steer_queues[task_id].put(prompt)
            return f"已向运行中的子智能体 {task_id} 发送继续消息。"

        task.goal = prompt
        task.status = TaskStatus.RUNNING
        if execution_mode:
            task.execution_mode = execution_mode
        task.run_in_background = task.execution_mode in {"async", "fork"}
        if not task.session_key:
            task.session_key = f"sub:{task.task_id}"
        self._store.save_task(task)
        if task.run_in_background:
            await self.execute_async(task)
            return f"子智能体 {task_id} 已继续执行（后台）。"
        return await self._run_task(task, self._new_steer_queue())

    def _new_steer_queue(self) -> asyncio.Queue[str]:
        return asyncio.Queue()

    async def _run_lifecycle(self, task: Task, steer_queue: asyncio.Queue[str]) -> None:
        """异步生命周期：执行并在结束后投递后台通知。"""
        try:
            result = await self._run_task(task, steer_queue)
            await self._lifecycle.mark_completed(task, result)

        except asyncio.CancelledError:
            await self._lifecycle.mark_cancelled(task)

        except Exception as e:
            logger.exception("子智能体执行失败: %s", task.task_id)
            await self._lifecycle.mark_failed(task, str(e))

        finally:
            self._running.pop(task.task_id, None)
            self._loops.pop(task.task_id, None)
            self._steer_queues.pop(task.task_id, None)

    async def _run_task(self, task: Task, steer_queue: asyncio.Queue[str] | None = None) -> str:
        """执行子智能体 ReAct 循环。"""
        self._store.update_task_status(task.task_id, TaskStatus.RUNNING)

        reporter = _InProcessReporter(self._store)
        tools = self._build_tools_for_task(task)
        session = self._sessions.get_or_create(task.session_key or f"sub:{task.task_id}")
        if not session.messages and task.context_mode == "inherit" and task.seed_messages_json:
            try:
                session.replace_history(json.loads(task.seed_messages_json))
                self._sessions.save(session)
            except Exception:
                logger.warning("子智能体 seed_messages_json 解析失败: %s", task.task_id)
        history_messages = session.get_history()

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

        result = await loop.run(task, history_messages=history_messages, steer_queue=steer_queue)
        session.add_message("user", task.goal)
        for message in loop.messages:
            role = str(message.get("role") or "")
            if role not in {"assistant", "tool", "user"}:
                continue
            payload = {k: v for k, v in message.items() if k != "role"}
            session.add_message(role, payload.pop("content", ""), **payload)
        session.add_message("assistant", result)
        self._sessions.save(session)
        return result

    def _build_tools_for_task(self, task: Task):
        registry = self._tool_builder(task)
        agent_def = find_agent(task.agent_type)
        if agent_def.tools and "*" not in agent_def.tools:
            allowed = set(agent_def.tools)
            for tool_name in list(registry.tool_names):
                if tool_name not in allowed:
                    registry.unregister(tool_name)
        for tool_name in agent_def.disallowed_tools:
            registry.unregister(tool_name)
        if task.agent_type == "coordinator" and registry.has("agent"):
            registry.set_metadata("agent", allow_in_subagent=True)
        return registry
