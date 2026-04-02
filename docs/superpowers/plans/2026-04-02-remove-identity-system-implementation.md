# Remove Identity System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completely remove AuraEve's identity system so runtime behavior no longer depends on canonical identity, owner relationships, or identity prompt injection.

**Architecture:** This is a deletion-first refactor. Remove identity handling from the runtime core first, then remove prompt and input metadata dependencies, then delete startup wiring and the standalone `auraeve/identity` subsystem. Keep session routing simple by using plain `channel`, `sender_id`, and `chat_id` fields only.

**Tech Stack:** Python, pytest, FastAPI/WebUI service layer, runtime queue scheduler, channel adapters, sqlite-backed session state

---

## File Map

### Runtime Core

- Modify: `auraeve/agent_runtime/kernel.py`
  - Remove identity resolver wiring, identity metadata enrichment, owner prefix logic, and identity snapshot persistence.
- Modify: `auraeve/agent_runtime/prompt/assembler.py`
  - Remove `identity_context` from the prompt assembly path.
- Modify: `auraeve/agent_runtime/prompt/__init__.py` if needed
  - Keep exports aligned if signatures change.

### Context/Engine Interfaces

- Modify: `auraeve/agent/engines/base.py`
- Modify: `auraeve/agent/engines/legacy.py`
- Modify: `auraeve/agent/engines/vector/engine.py`
- Modify: `auraeve/agent/context.py`
  - Remove identity-related prompt parameters and helper text.

### Input/Metadata

- Modify: `auraeve/webui/chat_service.py`
  - Remove `webui_display_name` identity metadata.
- Modify: `auraeve/channels/napcat.py`
  - Remove `is_owner` metadata and owner-specific branches.
- Modify: `auraeve/bus/events.py`
  - Simplify `InboundMessage.session_key`.

### Startup Wiring

- Modify: `main.py`
  - Remove identity subsystem setup, `identity.db`, owner binding logic, and kernel injection.

### Identity Subsystem

- Delete: `auraeve/identity/__init__.py`
- Delete: `auraeve/identity/models.py`
- Delete: `auraeve/identity/store.py`
- Delete: `auraeve/identity/service.py`
- Delete: `auraeve/identity/resolver.py`

### Tests

- Modify: `tests/test_kernel_resume.py`
- Modify: `tests/test_runtime_cleanup.py`
- Modify: `tests/test_chat_console_service.py` if metadata assertions need to shrink
- Modify: `tests/test_napcat_channel_extract_content.py` only if owner metadata assumptions exist
- Create: `tests/test_identity_removal.py`

---

### Task 1: Add identity-removal regression tests

**Files:**
- Create: `tests/test_identity_removal.py`
- Modify: `tests/test_runtime_cleanup.py`

- [ ] **Step 1: Write the failing tests**

```python
import subprocess

from auraeve.agent_runtime.kernel import RuntimeKernel


def test_kernel_has_no_identity_resolver_parameter() -> None:
    import inspect

    signature = inspect.signature(RuntimeKernel)
    assert "identity_resolver" not in signature.parameters


def test_no_identity_imports_left_in_production_code() -> None:
    result = subprocess.run(
        ["rg", "-n", "auraeve\\.identity|IdentityResolver|IdentityService|IdentityStore", "auraeve", "main.py"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1


def test_no_identity_metadata_fields_left_in_production_code() -> None:
    result = subprocess.run(
        ["rg", "-n", "canonical_user_id|relationship_to_assistant|identity_confidence|identity_source|webui_display_name|is_owner", "auraeve", "main.py"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_identity_removal.py tests/test_runtime_cleanup.py -q`
Expected: FAIL because `identity_resolver`, identity imports, and identity metadata references still exist.

- [ ] **Step 3: Write minimal implementation**

Implement only enough code changes to make the new scans and constructor expectations pass.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_identity_removal.py tests/test_runtime_cleanup.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_identity_removal.py tests/test_runtime_cleanup.py auraeve/agent_runtime/kernel.py main.py
git commit -m "test: add identity removal regression coverage"
```

### Task 2: Remove identity handling from runtime kernel

**Files:**
- Modify: `auraeve/agent_runtime/kernel.py`
- Modify: `tests/test_kernel_resume.py`

- [ ] **Step 1: Write the failing tests**

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from auraeve.agent_runtime.kernel import RuntimeKernel


@pytest.mark.asyncio
async def test_process_message_no_longer_builds_identity_context() -> None:
    kernel = object.__new__(RuntimeKernel)
    kernel._media_runtime = None
    kernel._plan = MagicMock(format_for_prompt=MagicMock(return_value=""))
    kernel._set_tool_context = MagicMock()
    kernel._set_media_understand_context = MagicMock()
    kernel._extract_attachments_legacy = AsyncMock(return_value=None)
    kernel._inject_plan_into_messages = MagicMock(side_effect=lambda messages, _: messages)
    kernel._sanitize_assistant_output = RuntimeKernel._sanitize_assistant_output
    kernel.sessions = MagicMock()
    session = MagicMock()
    session.key = "webui:chat-1"
    session.get_history.return_value = []
    kernel.sessions.get_or_create.return_value = session
    kernel.assembler = MagicMock()
    kernel.assembler.assemble = AsyncMock(return_value=MagicMock(messages=[], compacted_messages=None, estimated_tokens=0))
    kernel._orchestrator = MagicMock()
    kernel._orchestrator.run = AsyncMock(return_value=MagicMock(final_content="ok", tools_used=[], recovery_actions=[]))
    kernel.hooks = MagicMock(
        run_session_start=AsyncMock(),
        run_session_end=AsyncMock(),
        run_message_sending=AsyncMock(return_value=MagicMock(cancel=False, content="ok")),
    )
    kernel.engine = MagicMock(after_turn=AsyncMock())
    kernel.memory_lifecycle = None
    kernel.tools = MagicMock(tool_names=[])
    kernel.model = "model"
    kernel.temperature = 0.0
    kernel.max_tokens = 1000

    await RuntimeKernel._process_message(
        kernel,
        session_key="webui:chat-1",
        channel="webui",
        sender_id="user-1",
        chat_id="chat-1",
        content="hello",
        metadata={},
    )

    assemble_kwargs = kernel.assembler.assemble.await_args.kwargs
    assert "identity_context" not in assemble_kwargs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_kernel_resume.py::test_process_message_no_longer_builds_identity_context -q`
Expected: FAIL because the kernel still passes `identity_context`.

- [ ] **Step 3: Write minimal implementation**

Delete from `auraeve/agent_runtime/kernel.py`:

```python
if TYPE_CHECKING:
    from auraeve.identity.resolver import IdentityResolver
```

and remove:

```python
identity_resolver: "IdentityResolver | None" = None,
self._identity_resolver = identity_resolver
```

Then delete:

```python
def _resolve_identity_metadata(...): ...
def _build_identity_context(...): ...
```

and simplify `_process_message()` so it no longer:

- mutates identity metadata
- computes `identity_context`
- prepends `*★owner:*`
- builds `identity_snapshot`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_kernel_resume.py tests/test_identity_removal.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add auraeve/agent_runtime/kernel.py tests/test_kernel_resume.py tests/test_identity_removal.py
git commit -m "refactor: remove identity handling from runtime kernel"
```

### Task 3: Remove identity context from prompt and engine interfaces

**Files:**
- Modify: `auraeve/agent_runtime/prompt/assembler.py`
- Modify: `auraeve/agent/engines/base.py`
- Modify: `auraeve/agent/engines/legacy.py`
- Modify: `auraeve/agent/engines/vector/engine.py`
- Modify: `auraeve/agent/context.py`

- [ ] **Step 1: Write the failing tests**

```python
import subprocess


def test_no_identity_context_symbol_left_in_runtime_interfaces() -> None:
    result = subprocess.run(
        ["rg", "-n", "identity_context", "auraeve/agent_runtime", "auraeve/agent"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_identity_removal.py::test_no_identity_context_symbol_left_in_runtime_interfaces -q`
Expected: FAIL because prompt and engine interfaces still contain `identity_context`.

- [ ] **Step 3: Write minimal implementation**

Delete `identity_context` from these signatures and call paths:

```python
# auraeve/agent_runtime/prompt/assembler.py
identity_context: str | None = None

# auraeve/agent/engines/base.py
identity_context: str | None = None

# auraeve/agent/engines/legacy.py
identity_context: str | None = None

# auraeve/agent/engines/vector/engine.py
identity_context: str | None = None
```

Also remove any helper or prompt text in `auraeve/agent/context.py` that only exists to describe identity context.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_identity_removal.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add auraeve/agent_runtime/prompt/assembler.py auraeve/agent/engines/base.py auraeve/agent/engines/legacy.py auraeve/agent/engines/vector/engine.py auraeve/agent/context.py tests/test_identity_removal.py
git commit -m "refactor: remove identity context from prompt pipeline"
```

### Task 4: Remove identity metadata from WebUI and NapCat

**Files:**
- Modify: `auraeve/webui/chat_service.py`
- Modify: `auraeve/channels/napcat.py`
- Modify: `tests/test_chat_console_service.py`
- Modify: `tests/test_napcat_channel_extract_content.py` if needed
- Modify: `tests/test_identity_removal.py`

- [ ] **Step 1: Write the failing tests**

```python
import asyncio

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.session.manager import SessionManager
from auraeve.webui.chat_service import ChatService


async def test_webui_send_does_not_write_display_name_metadata(tmp_path):
    service = ChatService(
        session_manager=SessionManager(tmp_path),
        command_queue=RuntimeCommandQueue(),
    )
    await service.send("webui:chat-1", "hello", "idem-1", "user-1", display_name="Alice")
    queued = service._command_queue.snapshot()
    metadata = queued[0].payload["metadata"]
    assert "webui_display_name" not in metadata
```

and add a scan:

```python
def test_no_is_owner_metadata_injection_left() -> None:
    import subprocess
    result = subprocess.run(
        ["rg", "-n", "\"is_owner\"|metadata\\[\"is_owner\"\\]", "auraeve/channels/napcat.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_identity_removal.py tests/test_chat_console_service.py -q`
Expected: FAIL because `webui_display_name` and `is_owner` still exist.

- [ ] **Step 3: Write minimal implementation**

In `auraeve/webui/chat_service.py`, keep:

```python
metadata = {"run_id": run_id, "idempotency_key": idempotency_key, "webui_user_id": user_id}
```

but remove:

```python
if display_name:
    metadata["webui_display_name"] = display_name
```

In `auraeve/channels/napcat.py`, remove only the owner-specific metadata and owner-specific branches. Keep normal group filtering and `at_me` logic.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_identity_removal.py tests/test_chat_console_service.py tests/test_napcat_channel_extract_content.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add auraeve/webui/chat_service.py auraeve/channels/napcat.py tests/test_chat_console_service.py tests/test_napcat_channel_extract_content.py tests/test_identity_removal.py
git commit -m "refactor: remove identity metadata from inputs"
```

### Task 5: Simplify session key logic and startup wiring

**Files:**
- Modify: `auraeve/bus/events.py`
- Modify: `main.py`
- Modify: `tests/test_identity_removal.py`

- [ ] **Step 1: Write the failing tests**

```python
from auraeve.bus.events import InboundMessage


def test_inbound_message_session_key_uses_channel_and_chat_id_only() -> None:
    msg = InboundMessage(
        channel="webui",
        sender_id="user-1",
        chat_id="chat-1",
        content="hello",
        metadata={"canonical_user_id": "user:abc"},
    )

    assert msg.session_key == "webui:chat-1"
```

and add a scan:

```python
def test_main_has_no_identity_startup_wiring() -> None:
    import subprocess
    result = subprocess.run(
        ["rg", "-n", "identity_db|IdentityStore|IdentityService|IdentityResolver|OWNER_QQ|WEBUI_OWNER_USER_ID", "main.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_identity_removal.py -q`
Expected: FAIL because `InboundMessage.session_key` still prefers canonical identity and `main.py` still initializes identity services.

- [ ] **Step 3: Write minimal implementation**

Update `auraeve/bus/events.py`:

```python
@property
def session_key(self) -> str:
    if self.chat_id:
        return f"{self.channel}:{self.chat_id}"
    return self.sender_id or "global"
```

In `main.py`, delete:

- identity imports
- identity db setup
- owner binding code
- WebUI owner binding code
- `identity_resolver=identity_resolver`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_identity_removal.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add auraeve/bus/events.py main.py tests/test_identity_removal.py
git commit -m "refactor: remove identity startup wiring"
```

### Task 6: Delete the standalone identity subsystem

**Files:**
- Delete: `auraeve/identity/__init__.py`
- Delete: `auraeve/identity/models.py`
- Delete: `auraeve/identity/store.py`
- Delete: `auraeve/identity/service.py`
- Delete: `auraeve/identity/resolver.py`
- Modify: `tests/test_identity_removal.py`

- [ ] **Step 1: Write the failing tests**

```python
import os


def test_identity_package_removed() -> None:
    assert not os.path.exists("auraeve/identity")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_identity_removal.py::test_identity_package_removed -q`
Expected: FAIL because the directory still exists.

- [ ] **Step 3: Write minimal implementation**

Delete the entire `auraeve/identity` directory and any now-unused imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_identity_removal.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A auraeve/identity tests/test_identity_removal.py
git commit -m "refactor: delete identity subsystem"
```

### Task 7: Final regression and cleanup

**Files:**
- Modify: any touched files only if required by test failures

- [ ] **Step 1: Run focused regression tests**

Run:

```bash
python -m pytest tests/test_identity_removal.py tests/test_kernel_resume.py tests/test_runtime_cleanup.py tests/test_chat_console_service.py tests/test_napcat_channel_extract_content.py -q
```

Expected: all pass

- [ ] **Step 2: Run full test suite**

Run:

```bash
python -m pytest -q
```

Expected: all pass

- [ ] **Step 3: Run final source scans**

Run:

```bash
rg -n "auraeve\.identity|canonical_user_id|relationship_to_assistant|identity_confidence|identity_source|webui_display_name|is_owner" auraeve main.py
```

Expected: no matches in production runtime code

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: verify identity system removal"
```

## Self-Review

Spec coverage:

- runtime removal is covered in Tasks 2 and 3
- input metadata removal is covered in Task 4
- session key simplification and startup cleanup are covered in Task 5
- standalone subsystem deletion is covered in Task 6
- final regression and source scans are covered in Task 7

Placeholder scan:

- no `TODO` or `TBD`
- each task includes exact files, commands, and concrete test/code expectations

Type consistency:

- the plan removes `identity_resolver` rather than replacing it
- `identity_context` is removed across all interfaces in one pass
- session key rule is consistent with the approved spec
