from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from .command_queue import RuntimeCommandQueue
from .command_types import QueuedCommand


class RuntimeScheduler:
    def __init__(
        self,
        *,
        queue: RuntimeCommandQueue,
        run_command: Callable[[QueuedCommand], Awaitable[None]] | None,
    ) -> None:
        self._queue = queue
        self._run_command = run_command
        self._running = False
        self._busy = False
        self._wake_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._unsubscribe = self._queue.subscribe(self.notify_queue_changed)

    def notify_queue_changed(self) -> None:
        self._wake_event.set()

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        self._wake_event.set()
        if self._task is not None:
            await self._task
        self._unsubscribe()

    async def _loop(self) -> None:
        while self._running:
            await self._wake_event.wait()
            self._wake_event.clear()
            if self._busy or self._run_command is None:
                continue
            next_command = self._queue.dequeue_next()
            if next_command is None:
                continue
            self._busy = True
            try:
                await self._run_command(next_command)
            finally:
                self._busy = False
                if self._queue.snapshot_all():
                    self._wake_event.set()

    def snapshot_for_checkpoint(
        self,
        *,
        agent_id: str | None,
        is_main_thread: bool,
        max_priority: str,
        session_key: str | None = None,
    ) -> list[QueuedCommand]:
        return self._queue.snapshot_for_scope(
            max_priority=max_priority,
            agent_id=agent_id,
            is_main_thread=is_main_thread,
            session_key=session_key,
        )
