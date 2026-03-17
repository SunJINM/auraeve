"""LocalSubAgentExecutor：本地子体进程内执行器。"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from auraeve.subagents.data.models import Task, TaskStatus
from auraeve.subagents.runtime.react_loop import ReActLoop
from auraeve.subagents.runtime.reporter import InProcessReporter
from auraeve.subagents.runtime.local_memory import LocalMemoryStore

if TYPE_CHECKING:
    from auraeve.providers.base import LLMProvider
    from auraeve.agent.tools.registry import ToolRegistry
    from auraeve.agent_runtime.tool_policy.engine import ToolPolicyEngine
    from auraeve.subagents.control_plane.orchestrator import TaskOrchestrator


class LocalSubAgentExecutor:
    """将本地 asyncio.Task 包装为标准子体接口。"""

    def __init__(
        self,
        orchestrator: "TaskOrchestrator",
        provider: "LLMProvider",
        tool_builder,
        policy: "ToolPolicyEngine",
        workspace: Path,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        max_iterations: int = 50,
        thinking_budget_tokens: int | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._provider = provider
        self._tool_builder = tool_builder
        self._policy = policy
        self._workspace = workspace
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_iterations = max_iterations
        self._thinking_budget_tokens = thinking_budget_tokens
        self._running: dict[str, asyncio.Task] = {}
        self._loops: dict[str, ReActLoop] = {}
        self._steer_queues: dict[str, asyncio.Queue] = {}

    async def execute(self, task: Task) -> None:
        """派生本地 asyncio.Task 执行任务。"""
        steer_queue: asyncio.Queue = asyncio.Queue()
        self._steer_queues[task.task_id] = steer_queue

        reporter = InProcessReporter(orchestrator=self._orchestrator)
        memory = LocalMemoryStore(
            node_id="local",
            storage_dir=self._workspace / "memory" / "subagent_local",
        )

        tools = self._tool_builder(task)

        loop = ReActLoop(
            provider=self._provider,
            tools=tools,
            reporter=reporter,
            memory=memory,
            policy=self._policy,
            model=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            max_iterations=self._max_iterations,
            thinking_budget_tokens=self._thinking_budget_tokens,
            steer_queue=steer_queue,
        )
        self._loops[task.task_id] = loop

        bg_task = asyncio.create_task(self._run(task, loop))
        self._running[task.task_id] = bg_task
        bg_task.add_done_callback(lambda _: self._cleanup(task.task_id))

    async def _run(self, task: Task, loop: ReActLoop) -> None:
        logger.info(f"[local_executor] 本地子体启动: {task.task_id}")
        try:
            await loop.run(task)
        except asyncio.CancelledError:
            logger.info(f"[local_executor] 本地子体被取消: {task.task_id}")
        except Exception as e:
            logger.error(f"[local_executor] 本地子体异常: {task.task_id} - {e}")

    def pause(self, task_id: str) -> bool:
        loop = self._loops.get(task_id)
        if loop:
            loop.pause()
            return True
        return False

    def resume(self, task_id: str) -> bool:
        loop = self._loops.get(task_id)
        if loop:
            loop.resume()
            return True
        return False

    def cancel(self, task_id: str) -> bool:
        bg_task = self._running.get(task_id)
        if bg_task and not bg_task.done():
            bg_task.cancel()
            return True
        return False

    async def steer(self, task_id: str, message: str) -> bool:
        queue = self._steer_queues.get(task_id)
        if queue:
            await queue.put(message)
            return True
        return False

    def _cleanup(self, task_id: str) -> None:
        self._running.pop(task_id, None)
        self._loops.pop(task_id, None)
        self._steer_queues.pop(task_id, None)
