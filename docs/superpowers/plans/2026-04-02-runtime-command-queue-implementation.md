# Runtime Command Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 AuraEve 的运行时入站模型重构为 Claude Code 风格的单一命令队列入口，并将 `prompt`、`task-notification`、`cron`、`heartbeat` 四类输入统一到 `enqueue_command(...)`。

**Architecture:** 新增 `QueuedCommand`、`RuntimeCommandQueue`、`CommandProjection`、`RuntimeScheduler` 四个核心模块；将子智能体完成从 synthetic `tool_result` 改为队列事件；把 `RuntimeKernel` 收缩成“执行一个已调度回合”的核心，并在 turn loop 中加入检查点 drain。旧的 inbound `MessageBus` 和 `process_direct(...)` 退出生产路径。

**Tech Stack:** Python、asyncio、dataclasses、pytest

---

## File Map

### New files

- `d:\WorkProjects\auraeve\auraeve\agent_runtime\command_types.py`
- `d:\WorkProjects\auraeve\auraeve\agent_runtime\command_queue.py`
- `d:\WorkProjects\auraeve\auraeve\agent_runtime\command_projection.py`
- `d:\WorkProjects\auraeve\auraeve\agent_runtime\runtime_scheduler.py`
- `d:\WorkProjects\auraeve\tests\test_command_queue.py`
- `d:\WorkProjects\auraeve\tests\test_command_projection.py`
- `d:\WorkProjects\auraeve\tests\test_runtime_scheduler.py`

### Modified files

- `d:\WorkProjects\auraeve\auraeve\subagents\notification.py`
- `d:\WorkProjects\auraeve\auraeve\subagents\lifecycle.py`
- `d:\WorkProjects\auraeve\auraeve\agent_runtime\kernel.py`
- `d:\WorkProjects\auraeve\auraeve\agent_runtime\session_attempt.py`
- `d:\WorkProjects\auraeve\auraeve\channels\base.py`
- `d:\WorkProjects\auraeve\auraeve\webui\chat_service.py`
- `d:\WorkProjects\auraeve\main.py`
- `d:\WorkProjects\auraeve\tests\test_subagent_lifecycle.py`
- `d:\WorkProjects\auraeve\tests\test_notification.py`
- `d:\WorkProjects\auraeve\tests\test_kernel_orchestrator_wiring.py`
- `d:\WorkProjects\auraeve\tests\test_kernel_resume.py`
- `d:\WorkProjects\auraeve\tests\test_chat_console_service.py`

---

### Task 1: 建立命令模型与统一队列

**Files:**
- Create: `d:\WorkProjects\auraeve\auraeve\agent_runtime\command_types.py`
- Create: `d:\WorkProjects\auraeve\auraeve\agent_runtime\command_queue.py`
- Test: `d:\WorkProjects\auraeve\tests\test_command_queue.py`

- [ ] **Step 1: Write the failing tests**

```python
from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.agent_runtime.command_types import QueuedCommand


def _cmd(command_id: str, mode: str, priority: str, agent_id: str | None = None) -> QueuedCommand:
    return QueuedCommand(
        id=command_id,
        session_key="s1",
        source="test",
        mode=mode,
        priority=priority,
        payload={"text": command_id},
        origin={"kind": "test"},
        agent_id=agent_id,
    )


def test_queue_dequeues_by_priority_then_fifo() -> None:
    q = RuntimeCommandQueue()
    q.enqueue_command(_cmd("later-1", "prompt", "later"))
    q.enqueue_command(_cmd("next-1", "prompt", "next"))
    q.enqueue_command(_cmd("now-1", "prompt", "now"))
    assert q.dequeue_next().id == "now-1"
    assert q.dequeue_next().id == "next-1"
    assert q.dequeue_next().id == "later-1"


def test_snapshot_for_subagent_only_keeps_own_task_notifications() -> None:
    q = RuntimeCommandQueue()
    q.enqueue_command(_cmd("main-prompt", "prompt", "next"))
    q.enqueue_command(_cmd("sub-1-note", "task-notification", "next", agent_id="sub-1"))
    q.enqueue_command(_cmd("sub-2-note", "task-notification", "next", agent_id="sub-2"))
    snapshot = q.snapshot_for_scope(max_priority="next", agent_id="sub-1", is_main_thread=False)
    assert [cmd.id for cmd in snapshot] == ["sub-1-note"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_command_queue.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement command types**

Create `auraeve/agent_runtime/command_types.py`:

```python
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

CommandMode = Literal["prompt", "task-notification", "cron", "heartbeat"]
CommandPriority = Literal["now", "next", "later"]


@dataclass(slots=True)
class QueuedCommand:
    session_key: str
    source: str
    mode: CommandMode
    priority: CommandPriority
    payload: dict[str, Any]
    origin: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    agent_id: str | None = None
```

- [ ] **Step 4: Implement runtime command queue**

Create `auraeve/agent_runtime/command_queue.py`:

```python
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
                self._subscribers = [item for item in self._subscribers if item is not callback]
        return _unsubscribe

    def dequeue_next(self) -> QueuedCommand | None:
        with self._lock:
            if not self._queue:
                return None
            idx = min(range(len(self._queue)), key=lambda i: (_ORDER[self._queue[i].priority], i))
            return self._queue.pop(idx)

    def snapshot_for_scope(self, *, max_priority: str, agent_id: str | None, is_main_thread: bool) -> list[QueuedCommand]:
        ceiling = _ORDER[max_priority]
        with self._lock:
            items = [cmd for cmd in self._queue if _ORDER[cmd.priority] <= ceiling]
        if is_main_thread:
            return [cmd for cmd in items if cmd.agent_id is None]
        return [cmd for cmd in items if cmd.mode == "task-notification" and cmd.agent_id == agent_id]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_command_queue.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add auraeve/agent_runtime/command_types.py auraeve/agent_runtime/command_queue.py tests/test_command_queue.py
git commit -m "feat: add runtime command queue primitives"
```

---

### Task 2: 将 task-notification 改为后台事件语义

**Files:**
- Modify: `d:\WorkProjects\auraeve\auraeve\subagents\notification.py`
- Modify: `d:\WorkProjects\auraeve\auraeve\subagents\lifecycle.py`
- Create: `d:\WorkProjects\auraeve\auraeve\agent_runtime\command_projection.py`
- Test: `d:\WorkProjects\auraeve\tests\test_command_projection.py`
- Modify: `d:\WorkProjects\auraeve\tests\test_subagent_lifecycle.py`

- [ ] **Step 1: Write the failing tests**

```python
from auraeve.agent_runtime.command_projection import project_command_to_messages
from auraeve.agent_runtime.command_types import QueuedCommand


def test_task_notification_projects_to_background_event_message() -> None:
    cmd = QueuedCommand(
        id="n1",
        session_key="s1",
        source="subagent",
        mode="task-notification",
        priority="later",
        payload={"task_id": "task-1", "agent_type": "general-purpose", "goal": "collect", "status": "completed", "result": "done"},
        origin={"kind": "task-notification"},
    )
    messages = project_command_to_messages(cmd)
    assert messages[0]["role"] == "user"
    assert "background agent completed a task" in messages[0]["content"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_command_projection.py tests/test_subagent_lifecycle.py -v`
Expected: FAIL because projection module does not exist and lifecycle still resumes kernel directly

- [ ] **Step 3: Implement command projection**

Create `auraeve/agent_runtime/command_projection.py`:

```python
from __future__ import annotations

from .command_types import QueuedCommand


def project_command_to_messages(command: QueuedCommand) -> list[dict]:
    if command.mode == "prompt":
        return [{"role": "user", "content": str(command.payload.get("content", ""))}]
    if command.mode == "task-notification":
        payload = command.payload
        text = (
            "A background agent completed a task:\n"
            f"- task_id: {payload.get('task_id', '')}\n"
            f"- agent_type: {payload.get('agent_type', '')}\n"
            f"- goal: {payload.get('goal', '')}\n"
            f"- status: {payload.get('status', '')}\n"
            f"- result: {payload.get('result', '')}"
        )
        return [{"role": "user", "content": text}]
    return [{"role": "user", "content": str(command.payload.get('content', ''))}]
```

- [ ] **Step 4: Rewrite lifecycle to enqueue commands only**

Apply this shape in `auraeve/subagents/lifecycle.py`:

```python
from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.agent_runtime.command_types import QueuedCommand
```

```python
self._command_queue.enqueue_command(
    QueuedCommand(
        session_key=task.session_key or f"{task.origin_channel}:{task.origin_chat_id}",
        source="subagent",
        mode="task-notification",
        priority="later",
        payload=notification.to_payload(),
        origin={"kind": "task-notification", "is_system_generated": True},
    )
)
```

Delete the callback field and `_try_inject_result()`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_command_projection.py tests/test_subagent_lifecycle.py tests/test_notification.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add auraeve/subagents/notification.py auraeve/subagents/lifecycle.py auraeve/agent_runtime/command_projection.py tests/test_command_projection.py tests/test_subagent_lifecycle.py tests/test_notification.py
git commit -m "refactor: queue subagent completion as task notification events"
```

---

### Task 3: 引入 RuntimeScheduler 并验证 idle 唤醒与 checkpoint snapshot

**Files:**
- Create: `d:\WorkProjects\auraeve\auraeve\agent_runtime\runtime_scheduler.py`
- Test: `d:\WorkProjects\auraeve\tests\test_runtime_scheduler.py`
- Modify: `d:\WorkProjects\auraeve\tests\test_kernel_orchestrator_wiring.py`

- [ ] **Step 1: Write the failing tests**

```python
import asyncio

import pytest

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.agent_runtime.command_types import QueuedCommand
from auraeve.agent_runtime.runtime_scheduler import RuntimeScheduler


@pytest.mark.asyncio
async def test_scheduler_runs_next_command_when_idle() -> None:
    queue = RuntimeCommandQueue()
    seen: list[str] = []

    async def runner(command: QueuedCommand) -> None:
        seen.append(command.id)

    scheduler = RuntimeScheduler(queue=queue, run_command=runner)
    await scheduler.start()
    queue.enqueue_command(
        QueuedCommand(
            id="cmd-1",
            session_key="s1",
            source="test",
            mode="prompt",
            priority="next",
            payload={"content": "hello"},
            origin={"kind": "user"},
        )
    )
    await asyncio.sleep(0.05)
    await scheduler.stop()
    assert seen == ["cmd-1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_runtime_scheduler.py tests/test_kernel_orchestrator_wiring.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement RuntimeScheduler**

Create `auraeve/agent_runtime/runtime_scheduler.py`:

```python
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from .command_queue import RuntimeCommandQueue
from .command_types import QueuedCommand


class RuntimeScheduler:
    def __init__(self, *, queue: RuntimeCommandQueue, run_command: Callable[[QueuedCommand], Awaitable[None]] | None) -> None:
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
        if self._task:
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
                if self._queue.snapshot_for_scope(max_priority="later", agent_id=None, is_main_thread=True):
                    self._wake_event.set()

    def snapshot_for_checkpoint(self, *, agent_id: str | None, is_main_thread: bool, max_priority: str) -> list[QueuedCommand]:
        return self._queue.snapshot_for_scope(max_priority=max_priority, agent_id=agent_id, is_main_thread=is_main_thread)
```

- [ ] **Step 4: Update wiring test**

Replace `tests/test_kernel_orchestrator_wiring.py` expectations with:

```python
def test_kernel_exposes_command_queue_and_scheduler(kernel) -> None:
    assert kernel.command_queue is not None
    assert kernel.scheduler is not None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_runtime_scheduler.py tests/test_kernel_orchestrator_wiring.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add auraeve/agent_runtime/runtime_scheduler.py tests/test_runtime_scheduler.py tests/test_kernel_orchestrator_wiring.py
git commit -m "feat: add runtime scheduler for queue-driven execution"
```

---

### Task 4: 收缩 RuntimeKernel，并把 checkpoint drain 接入 turn loop

**Files:**
- Modify: `d:\WorkProjects\auraeve\auraeve\agent_runtime\kernel.py`
- Modify: `d:\WorkProjects\auraeve\auraeve\agent_runtime\session_attempt.py`
- Modify: `d:\WorkProjects\auraeve\tests\test_kernel_resume.py`

- [ ] **Step 1: Write the failing tests**

```python
import pytest


@pytest.mark.asyncio
async def test_kernel_execute_command_processes_prompt_without_process_direct(kernel) -> None:
    command = kernel.command_factory(
        session_key="webui:s1",
        source="webui",
        mode="prompt",
        priority="next",
        payload={"content": "hello"},
        origin={"kind": "user"},
    )
    result = await kernel.execute_command(command)
    assert result is not None


def test_kernel_has_no_process_direct(kernel) -> None:
    assert not hasattr(kernel, "process_direct")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_kernel_resume.py tests/test_kernel_orchestrator_wiring.py -v`
Expected: FAIL because `process_direct` still exists and `execute_command` does not

- [ ] **Step 3: Make kernel command-driven**

Add imports in `auraeve/agent_runtime/kernel.py`:

```python
from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.agent_runtime.command_projection import project_command_to_messages
from auraeve.agent_runtime.command_types import QueuedCommand
from auraeve.agent_runtime.runtime_scheduler import RuntimeScheduler
```

Add in `__init__`:

```python
self.command_queue = RuntimeCommandQueue()
self.scheduler = RuntimeScheduler(queue=self.command_queue, run_command=self.execute_command)
```

Add APIs:

```python
def command_factory(self, **kwargs) -> QueuedCommand:
    return QueuedCommand(**kwargs)


async def execute_command(self, command: QueuedCommand):
    await self._mcp_runtime.start()
    projected = project_command_to_messages(command)
    return await self._process_projected_command(command, projected)
```

Delete:

- inbound-bus `run()` loop
- `_register_subagent_resume()`
- `process_direct(...)`

- [ ] **Step 4: Add checkpoint drain hook to SessionAttemptRunner**

Apply this shape in `auraeve/agent_runtime/session_attempt.py`:

```python
def __init__(..., checkpoint_drain=None) -> None:
    ...
    self._checkpoint_drain = checkpoint_drain
```

Before `self._provider.chat(...)`:

```python
if self._checkpoint_drain is not None:
    drained_messages = self._checkpoint_drain(thread_id=thread_id, is_subagent=is_subagent)
    if drained_messages:
        msgs.extend(drained_messages)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_kernel_resume.py tests/test_kernel_orchestrator_wiring.py tests/test_prompt_assembler_extra.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add auraeve/agent_runtime/kernel.py auraeve/agent_runtime/session_attempt.py tests/test_kernel_resume.py
git commit -m "refactor: make kernel command-driven and add checkpoint draining"
```

---

### Task 5: 迁移 4 类消息源到 enqueue_command

**Files:**
- Modify: `d:\WorkProjects\auraeve\auraeve\channels\base.py`
- Modify: `d:\WorkProjects\auraeve\auraeve\webui\chat_service.py`
- Modify: `d:\WorkProjects\auraeve\main.py`
- Modify: `d:\WorkProjects\auraeve\tests\test_chat_console_service.py`

- [ ] **Step 1: Write the failing integration test**

```python
import pytest

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.webui.chat_service import ChatService


@pytest.mark.asyncio
async def test_chat_service_enqueues_prompt_command(session_manager) -> None:
    queue = RuntimeCommandQueue()
    service = ChatService(session_manager=session_manager, command_queue=queue)
    _, status = await service.send(
        session_key="webui:s1",
        message="hello",
        idempotency_key="idem-1",
        user_id="u1",
    )
    assert status == "started"
    commands = queue.snapshot_for_scope(max_priority="later", agent_id=None, is_main_thread=True)
    assert len(commands) == 1
    assert commands[0].mode == "prompt"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chat_console_service.py -v`
Expected: FAIL because `ChatService` still depends on `bus`

- [ ] **Step 3: Migrate BaseChannel and ChatService**

Apply this shape in `auraeve/channels/base.py`:

```python
from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.agent_runtime.command_types import QueuedCommand
```

```python
self.command_queue.enqueue_command(
    QueuedCommand(
        session_key=f"{self.name}:{chat_id}",
        source=self.name,
        mode="prompt",
        priority="next",
        payload={"content": content, "channel": self.name, "sender_id": str(sender_id), "chat_id": str(chat_id), "media": media or [], "attachments": attachments or [], "metadata": metadata or {}},
        origin={"kind": "user"},
    )
)
```

Apply the same queue-based pattern in `auraeve/webui/chat_service.py`.

- [ ] **Step 4: Migrate cron and heartbeat**

Replace direct execution in `main.py` with:

```python
agent.command_queue.enqueue_command(
    agent.command_factory(
        session_key=f"cron:{job.id}",
        source="cron",
        mode="cron",
        priority="later",
        payload={"content": job.payload.message, "job_id": job.id},
        origin={"kind": "cron", "is_system_generated": True},
    )
)
```

And:

```python
on_heartbeat=lambda prompt: agent.command_queue.enqueue_command(
    agent.command_factory(
        session_key="heartbeat:main",
        source="heartbeat",
        mode="heartbeat",
        priority="later",
        payload={"content": prompt},
        origin={"kind": "heartbeat", "is_system_generated": True},
    )
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_chat_console_service.py tests/test_subagent_lifecycle.py tests/test_runtime_scheduler.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add auraeve/channels/base.py auraeve/webui/chat_service.py main.py tests/test_chat_console_service.py
git commit -m "refactor: route prompt cron and heartbeat through command queue"
```

---

### Task 6: 清理旧 inbound 路径并完成回归

**Files:**
- Modify: `d:\WorkProjects\auraeve\auraeve\bus\queue.py`
- Modify: `d:\WorkProjects\auraeve\main.py`
- Modify: `d:\WorkProjects\auraeve\auraeve\channels\webui.py`
- Modify: `d:\WorkProjects\auraeve\tests\test_kernel_resume.py`

- [ ] **Step 1: Write the failing cleanup test**

```python
def test_no_publish_inbound_call_sites_left() -> None:
    import subprocess
    result = subprocess.run(
        ["rg", "-n", "publish_inbound\\(", "auraeve", "main.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_kernel_resume.py::test_no_publish_inbound_call_sites_left -v`
Expected: FAIL because `publish_inbound(` still exists

- [ ] **Step 3: Retire inbound MessageBus production path**

Keep only outbound delivery in `auraeve/bus/queue.py`:

```python
class MessageBus:
    def __init__(self):
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        self._outbound_subscribers = {}
        self._running = False
```

Delete:

- `inbound`
- `publish_inbound()`
- `consume_inbound()`

Update `main.py` startup/shutdown to start and stop `agent.scheduler`.

- [ ] **Step 4: Run targeted regression suite**

Run: `pytest tests/test_command_queue.py tests/test_command_projection.py tests/test_runtime_scheduler.py tests/test_subagent_lifecycle.py tests/test_notification.py tests/test_kernel_resume.py tests/test_kernel_orchestrator_wiring.py tests/test_chat_console_service.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add auraeve/bus/queue.py main.py auraeve/channels/webui.py tests/test_kernel_resume.py tests/test_command_queue.py tests/test_command_projection.py tests/test_runtime_scheduler.py
git commit -m "refactor: remove inbound bus path and finish command queue migration"
```

---

## Self-Review

### Spec coverage

- Single inbound API `enqueue_command(...)`: Task 1, Task 4, Task 5, Task 6
- Four approved sources: Task 2, Task 5
- Remove `process_direct(...)`: Task 4
- Remove direct subagent resume callback: Task 2, Task 4
- Idle wakeup and checkpoint drain: Task 3, Task 4
- Retire inbound `MessageBus`: Task 6

### Placeholder scan

- No `TODO`/`TBD` placeholders remain
- All tasks contain exact file paths, commands, and concrete code blocks

### Type consistency

- Queue model uses `QueuedCommand`
- Entry API uses `enqueue_command(...)`
- Scheduler API uses `snapshot_for_checkpoint(...)`
- Lifecycle emits `task-notification` command payloads rather than synthetic tool messages
