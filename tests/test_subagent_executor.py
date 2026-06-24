"""子智能体执行器测试。"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.subagents.data.models import Task, TaskStatus
from auraeve.subagents.executor import SubagentExecutor


@pytest.fixture
def store(tmp_path):
    from auraeve.subagents.data.repositories import SubagentStore
    return SubagentStore(str(tmp_path / "test.db"))


@pytest.fixture
def command_queue():
    return RuntimeCommandQueue()


@pytest.fixture
def executor(store, command_queue):
    return SubagentExecutor(
        store=store,
        command_queue=command_queue,
        provider=MagicMock(),
        tool_builder=MagicMock(return_value=MagicMock()),
        policy=MagicMock(),
        model="test-model",
        max_concurrent=3,
        sessions_dir=store._db_path if False else None,
    )


def test_executor_init(executor):
    assert executor._max_concurrent == 3
    assert len(executor._running) == 0


def test_create_task(executor):
    task = executor.create_task(
        goal="测试任务",
        agent_type="general-purpose",
        origin_channel="test",
        origin_chat_id="chat1",
        spawn_tool_call_id="call_1",
    )
    assert task.task_id is not None
    assert task.goal == "测试任务"
    assert task.status == TaskStatus.QUEUED

    loaded = executor._store.get_task(task.task_id)
    assert loaded is not None
    assert loaded.goal == "测试任务"
    assert loaded.execution_mode == "sync"
    assert loaded.context_mode == "fresh"
    assert loaded.session_key.startswith("sub:")
    assert not hasattr(loaded, "budget")


def test_create_task_respects_max_concurrent(executor):
    executor._max_concurrent = 1
    executor._running["fake"] = MagicMock()
    with pytest.raises(RuntimeError, match="并发"):
        executor.create_task(goal="新任务", origin_channel="test", origin_chat_id="c1")


def test_list_tasks(executor):
    executor.create_task(goal="任务1", origin_channel="t", origin_chat_id="c")
    executor.create_task(goal="任务2", origin_channel="t", origin_chat_id="c")
    tasks = executor.list_tasks()
    assert len(tasks) == 2


def test_get_task(executor):
    task = executor.create_task(goal="查询测试", origin_channel="t", origin_chat_id="c")
    loaded = executor.get_task(task.task_id)
    assert loaded is not None
    assert loaded.goal == "查询测试"


def test_cancel_nonexistent(executor):
    assert executor.cancel_task("nonexistent") is False


@pytest.mark.asyncio
async def test_continue_running_task_pushes_steer_queue(executor):
    task = executor.create_task(goal="运行中任务", origin_channel="t", origin_chat_id="c")
    executor._steer_queues[task.task_id] = executor._new_steer_queue()
    executor._running[task.task_id] = AsyncMock()

    message = await executor.continue_task(task.task_id, "继续收集信息")

    assert "运行中" in message
    queued = executor._steer_queues[task.task_id].get_nowait()
    assert queued == "继续收集信息"


@pytest.mark.asyncio
async def test_continue_completed_task_reuses_existing_session(executor, monkeypatch):
    task = executor.create_task(goal="第一次任务", origin_channel="t", origin_chat_id="c")
    task.status = TaskStatus.COMPLETED
    executor._store.save_task(task)

    session = executor._sessions.get_or_create(task.session_key)
    session.add_message("user", "历史问题")
    session.add_message("assistant", "历史回答")
    executor._sessions.save(session)

    monkeypatch.setattr(executor, "_run_task", AsyncMock(return_value="继续执行结果"))

    result = await executor.continue_task(task.task_id, "继续这个任务")

    assert result == "继续执行结果"
    executor._run_task.assert_awaited_once()


def test_create_fork_task_uses_inherit_context(executor):
    task = executor.create_task(
        goal="检查当前上下文",
        agent_type="general-purpose",
        execution_mode="fork",
        context_mode="inherit",
        seed_messages=[{"role": "user", "content": "seed"}],
        origin_channel="t",
        origin_chat_id="c",
    )
    assert task.execution_mode == "fork"
    assert task.context_mode == "inherit"
    assert task.seed_messages_json.startswith("[")


def test_create_task_rejects_coordinator_spawning_coordinator(executor):
    with pytest.raises(ValueError, match="coordinator"):
        executor.create_task(
            goal="递归协调",
            agent_type="coordinator",
            caller_agent_type="coordinator",
            parent_task_id="parent-1",
            origin_channel="t",
            origin_chat_id="c",
        )


def test_create_task_allows_coordinator_spawning_worker(executor):
    task = executor.create_task(
        goal="执行子任务",
        agent_type="worker",
        caller_agent_type="coordinator",
        parent_task_id="parent-1",
        origin_channel="t",
        origin_chat_id="c",
    )

    assert task.parent_task_id == "parent-1"


def test_executor_resolves_explicit_model_card(executor, monkeypatch):
    provider = MagicMock(name="fast-provider")
    executor.configure_model_registry(
        [
            {
                "id": "main",
                "enabled": True,
                "isPrimary": True,
                "model": "main-model",
                "apiKey": "k-main",
                "maxTokens": 100,
            },
            {
                "id": "fast",
                "enabled": True,
                "isPrimary": False,
                "model": "fast-model",
                "apiKey": "k-fast",
                "maxTokens": 50,
                "temperature": 0.2,
                "thinkingBudgetTokens": 8,
            },
        ],
        provider_factory=lambda _card: provider,
    )
    task = Task(task_id="t-model", goal="模型测试", agent_type="worker", model_id="fast")

    resolved = executor._resolve_model_for_task(task)  # noqa: SLF001

    assert resolved.provider is provider
    assert resolved.model == "fast-model"
    assert resolved.max_tokens == 50
    assert resolved.temperature == 0.2
    assert resolved.thinking_budget_tokens == 8


def test_executor_explicit_missing_model_returns_visible_error(executor):
    executor.configure_model_registry(
        [{"id": "main", "enabled": True, "isPrimary": True, "model": "main-model", "apiKey": "k"}],
        provider_factory=lambda _card: MagicMock(),
    )
    task = Task(task_id="t-model", goal="模型测试", agent_type="worker", model_id="missing")

    with pytest.raises(ValueError, match="missing"):
        executor._resolve_model_for_task(task)  # noqa: SLF001


def test_executor_explicit_model_provider_failure_returns_visible_error(executor):
    def fail_provider(_card):
        raise RuntimeError("missing api key")

    executor.configure_model_registry(
        [
            {"id": "main", "enabled": True, "isPrimary": True, "model": "main-model", "apiKey": "k"},
            {"id": "fast", "enabled": True, "isPrimary": False, "model": "fast-model", "apiKey": ""},
        ],
        provider_factory=fail_provider,
    )
    task = Task(task_id="t-model", goal="模型测试", agent_type="worker", model_id="fast")

    with pytest.raises(ValueError, match="fast"):
        executor._resolve_model_for_task(task)  # noqa: SLF001


def test_executor_role_model_provider_failure_falls_back_to_primary(executor, monkeypatch):
    main_provider = MagicMock(name="main-provider")

    def provider_factory(card):
        if card["id"] == "fast":
            raise RuntimeError("missing api key")
        return MagicMock(name=f"provider-{card['id']}")

    executor._provider = main_provider
    executor.configure_model_registry(
        [
            {"id": "main", "enabled": True, "isPrimary": True, "model": "main-model", "apiKey": "k-main"},
            {"id": "fast", "enabled": True, "isPrimary": False, "model": "fast-model", "apiKey": ""},
        ],
        provider_factory=provider_factory,
    )
    agent_def = MagicMock(model="fast")
    monkeypatch.setattr("auraeve.subagents.executor.find_agent", lambda _agent_type: agent_def)
    task = Task(task_id="t-model", goal="模型测试", agent_type="worker")

    resolved = executor._resolve_model_for_task(task)  # noqa: SLF001

    assert resolved.provider is main_provider
    assert resolved.model == "main-model"


def test_executor_resolves_agent_model_override(executor, monkeypatch):
    agent_def = MagicMock(model="fast")
    monkeypatch.setattr("auraeve.subagents.executor.find_agent", lambda _agent_type: agent_def)
    task = Task(task_id="t-model", goal="模型测试", agent_type="custom-worker")

    assert executor._model_id_for_task(task) == "fast"  # noqa: SLF001


def test_executor_inherits_parent_model_when_agent_model_is_inherit(executor, monkeypatch):
    agent_def = MagicMock(model="inherit")
    monkeypatch.setattr("auraeve.subagents.executor.find_agent", lambda _agent_type: agent_def)
    task = Task(task_id="t-model", goal="模型测试", agent_type="worker")

    assert executor._model_id_for_task(task) == ""  # noqa: SLF001


@pytest.mark.asyncio
async def test_async_model_resolution_without_registry_inherits_parent_model(executor):
    parent_provider = executor._provider
    task = Task(task_id="t-model", goal="模型测试", agent_type="worker")

    resolved = await executor.resolve_model_for_task(task)

    assert resolved.provider is parent_provider
    assert resolved.model == "test-model"


@pytest.mark.asyncio
async def test_run_task_marks_model_resolution_error_failed(executor):
    task = executor.create_task(
        goal="模型测试",
        agent_type="worker",
        model_id="missing",
        origin_channel="t",
        origin_chat_id="c",
    )

    result = await executor._run_task(task)  # noqa: SLF001
    loaded = executor.get_task(task.task_id)

    assert result.startswith("错误:")
    assert loaded.status == TaskStatus.FAILED
    assert loaded.result == result


@pytest.mark.asyncio
async def test_execute_sync_promotes_to_background_on_timeout(executor, command_queue, monkeypatch):
    import asyncio
    import auraeve.subagents.executor as executor_module

    monkeypatch.setattr(executor_module, "_SYNC_TIMEOUT_S", 0.05)

    finished = asyncio.Event()

    async def slow_run_task(task, steer_queue=None):
        try:
            await asyncio.sleep(0.2)
            return "迟到的结果"
        finally:
            finished.set()

    monkeypatch.setattr(executor, "_run_task", slow_run_task)
    task = executor.create_task(goal="慢任务", agent_type="worker", execution_mode="sync")

    result = await executor.execute_sync(task)

    # 超时不中断，转为后台并给出可见提示
    assert "后台" in result
    assert task.task_id in result
    assert task.run_in_background is True
    assert task.execution_mode == "async"

    # 后台执行真正结束后应投递完成通知
    await asyncio.wait_for(finished.wait(), timeout=2)
    for _ in range(100):
        if command_queue.snapshot_all():
            break
        await asyncio.sleep(0.01)
    commands = command_queue.snapshot_all()
    assert any(
        c.mode == "task-notification" and c.payload.get("status") == "completed"
        for c in commands
    )


@pytest.mark.asyncio
async def test_execute_sync_returns_result_when_within_timeout(executor):
    async def quick_run_task(task, steer_queue=None):
        return "及时完成"

    executor._run_task = quick_run_task  # noqa: SLF001
    task = executor.create_task(goal="快任务", agent_type="worker", execution_mode="sync")

    result = await executor.execute_sync(task)

    assert result == "及时完成"
    assert task.task_id not in executor._running
