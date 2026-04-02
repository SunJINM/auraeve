from __future__ import annotations

import threading
from collections.abc import Callable

from .command_types import QueuedCommand

_ORDER = {"now": 0, "next": 1, "later": 2}


class RuntimeCommandQueue:
    def __init__(self) -> None:
        self._queue: list[QueuedCommand] = []
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[], None]] = []

    def enqueue_command(self, command: QueuedCommand) -> None:
        with self._lock:
            self._queue.append(command)
            subscribers = list(self._subscribers)
        for callback in subscribers:
            callback()

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(callback)

        def _unsubscribe() -> None:
            with self._lock:
                self._subscribers = [
                    item for item in self._subscribers if item is not callback
                ]

        return _unsubscribe

    def dequeue_next(self) -> QueuedCommand | None:
        with self._lock:
            if not self._queue:
                return None
            idx = min(
                range(len(self._queue)),
                key=lambda i: (_ORDER[self._queue[i].priority], i),
            )
            return self._queue.pop(idx)

    def snapshot_all(self) -> list[QueuedCommand]:
        with self._lock:
            return list(self._queue)

    def snapshot_for_scope(
        self,
        *,
        max_priority: str,
        agent_id: str | None,
        is_main_thread: bool,
        session_key: str | None = None,
    ) -> list[QueuedCommand]:
        ceiling = _ORDER[max_priority]
        with self._lock:
            items = [
                cmd for cmd in self._queue if _ORDER[cmd.priority] <= ceiling
            ]
        if session_key is not None:
            items = [cmd for cmd in items if cmd.session_key == session_key]
        if is_main_thread:
            return [cmd for cmd in items if cmd.agent_id is None]
        return [
            cmd for cmd in items
            if cmd.mode == "task-notification" and cmd.agent_id == agent_id
        ]

    def remove_commands(self, consumed: list[QueuedCommand]) -> None:
        if not consumed:
            return
        consumed_ids = {id(item) for item in consumed}
        with self._lock:
            self._queue = [
                cmd for cmd in self._queue if id(cmd) not in consumed_ids
            ]
