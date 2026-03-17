"""远程子体入口：连接母体，接收任务，执行 ReAct 循环。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from auraeve.subagents.data.models import Task, TaskBudget
from auraeve.subagents.runtime.react_loop import ReActLoop
from auraeve.subagents.runtime.local_memory import LocalMemoryStore
from auraeve.subagents.runtime.capabilities import CapabilityRegistry
from auraeve.subagents.transport.ws_client import SubAgentWSClient
from .reporter import WebSocketReporter


class RemoteSubAgentRunner:
    """远程子体运行器。

    连接母体 WebSocket，接收任务分配，在本地执行 ReAct 循环，
    通过 WebSocketReporter 上报进度和结果。
    """

    def __init__(
        self,
        node_id: str,
        token: str,
        mother_url: str,
        provider: Any,
        tool_builder: Any,
        policy: Any,
        workspace: Path,
        display_name: str = "",
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        max_iterations: int = 50,
        thinking_budget_tokens: int | None = None,
    ) -> None:
        self._node_id = node_id
        self._provider = provider
        self._tool_builder = tool_builder
        self._policy = policy
        self._workspace = workspace
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_iterations = max_iterations
        self._thinking_budget_tokens = thinking_budget_tokens

        caps = CapabilityRegistry.default_local()

        self._reporter: WebSocketReporter | None = None
        self._client = SubAgentWSClient(
            node_id=node_id,
            token=token,
            mother_url=mother_url,
            display_name=display_name or node_id,
            platform=sys.platform,
            capabilities=caps.to_json(),
            on_task_assign=self._on_task_assign,
            on_task_pause=self._on_task_pause,
            on_task_resume=self._on_task_resume,
            on_task_cancel=self._on_task_cancel,
            on_approval_decide=self._on_approval_decide,
        )

        self._running_tasks: dict[str, asyncio.Task] = {}
        self._loops: dict[str, ReActLoop] = {}

    async def start(self) -> None:
        """启动远程子体，连接母体。"""
        self._reporter = WebSocketReporter(self._client)
        logger.info(f"[remote_runner] 远程子体 {self._node_id} 启动")
        await self._client.connect()

    def stop(self) -> None:
        self._client.disconnect()
        for task in self._running_tasks.values():
            if not task.done():
                task.cancel()

    async def _on_task_assign(self, msg: dict) -> None:
        task_id = msg["task_id"]
        goal = msg.get("goal", "")
        budget_raw = msg.get("budget", {})

        task = Task(
            task_id=task_id,
            goal=goal,
            budget=TaskBudget(
                max_steps=budget_raw.get("max_steps", 50),
                max_duration_s=budget_raw.get("max_duration_s", 600),
                max_tool_calls=budget_raw.get("max_tool_calls", 100),
                max_tokens=budget_raw.get("max_tokens", 120_000),
            ),
        )

        memory = LocalMemoryStore(
            node_id=self._node_id,
            storage_dir=self._workspace / "memory" / f"subagent_{self._node_id}",
        )

        tools = self._tool_builder(task)

        loop = ReActLoop(
            provider=self._provider,
            tools=tools,
            reporter=self._reporter,
            memory=memory,
            policy=self._policy,
            model=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            max_iterations=self._max_iterations,
            thinking_budget_tokens=self._thinking_budget_tokens,
        )
        self._loops[task_id] = loop

        bg = asyncio.create_task(self._execute(task, loop))
        self._running_tasks[task_id] = bg
        bg.add_done_callback(lambda _: self._cleanup(task_id))

    async def _execute(self, task: Task, loop: ReActLoop) -> None:
        logger.info(f"[remote_runner] 开始执行任务: {task.task_id}")
        try:
            await loop.run(task)
        except asyncio.CancelledError:
            logger.info(f"[remote_runner] 任务被取消: {task.task_id}")
        except Exception as e:
            logger.error(f"[remote_runner] 任务异常: {task.task_id} - {e}")

    async def _on_task_pause(self, task_id: str) -> None:
        loop = self._loops.get(task_id)
        if loop:
            loop.pause()

    async def _on_task_resume(self, task_id: str) -> None:
        loop = self._loops.get(task_id)
        if loop:
            loop.resume()

    async def _on_task_cancel(self, task_id: str) -> None:
        bg = self._running_tasks.get(task_id)
        if bg and not bg.done():
            bg.cancel()

    async def _on_approval_decide(self, approval_id: str, decision: str) -> None:
        if self._reporter:
            self._reporter.resolve_approval(approval_id, decision)

    def _cleanup(self, task_id: str) -> None:
        self._running_tasks.pop(task_id, None)
        self._loops.pop(task_id, None)
