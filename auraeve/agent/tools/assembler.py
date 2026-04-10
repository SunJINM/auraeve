from __future__ import annotations

from pathlib import Path

from auraeve.agent.tasks import TaskStore
from auraeve.agent.tools.cron import CronTool
from auraeve.agent.tools.filesystem import EditTool, ReadTool, WriteTool
from auraeve.agent.tools.plan import TodoTool
from auraeve.agent.tools.search import GlobTool, GrepTool
from auraeve.agent.tools.task_create import TaskCreateTool
from auraeve.agent.tools.task_get import TaskGetTool
from auraeve.agent.tools.task_list import TaskListTool
from auraeve.agent.tools.task_update import TaskUpdateTool
from auraeve.agent.tools.registry import ToolRegistry
from auraeve.agent.tools.shell import BashTool
from auraeve.agent.tools.agent_tool import AgentTool
from auraeve.agent.tools.web import WebFetchTool, WebSearchTool
from auraeve.config.paths import resolve_state_dir
from auraeve.execution.dispatcher import ExecutionDispatcher


def _resolve_task_base_dir(task_base_dir: Path | None) -> Path:
    if task_base_dir is not None:
        return Path(task_base_dir)
    return resolve_state_dir() / "tasks"


def register_task_tools(
    registry: ToolRegistry,
    *,
    task_mode: str,
    plan_manager,
    task_session_key: str | None,
    task_base_dir: Path | None = None,
) -> None:
    if task_mode == "task_v2":
        if not task_session_key:
            raise ValueError("task_session_key is required when task_mode='task_v2'")
        store = TaskStore(
            base_dir=_resolve_task_base_dir(task_base_dir),
            task_list_id=task_session_key,
        )
        registry.register(TaskCreateTool(store))
        registry.register(TaskGetTool(store))
        registry.register(TaskUpdateTool(store))
        registry.register(TaskListTool(store))
        return

    if task_mode == "legacy_todo":
        todo_tool = TodoTool(plan_manager=plan_manager)
        if task_session_key:
            todo_tool.set_thread_id(task_session_key)
        registry.register(todo_tool)


def build_tool_registry(
    *,
    profile: str,
    workspace: Path,
    restrict_to_workspace: bool,
    exec_timeout: int,
    brave_api_key: str | None,
    tavily_api_key: str | None = None,
    bus_publish_outbound,
    provider,
    model: str,
    plan_manager,
    channel_users: dict[str, str] | None = None,
    notify_channel: str = "",
    subagent_executor=None,
    cron_service=None,
    origin_channel: str | None = None,
    origin_chat_id: str | None = None,
    thread_id: str | None = None,
    engine=None,
    execution_workspace: str | None = None,
    execution_dispatcher: ExecutionDispatcher | None = None,
    task_mode: str = "legacy_todo",
    task_session_key: str | None = None,
    task_base_dir: Path | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    tool_workspace = execution_workspace or str(workspace)
    dispatcher = execution_dispatcher or ExecutionDispatcher()
    allowed_dir = None
    if restrict_to_workspace:
        allowed_dir = Path(tool_workspace)

    registry.register(ReadTool(allowed_dir=allowed_dir, dispatcher=dispatcher))
    registry.register(WriteTool(allowed_dir=allowed_dir, dispatcher=dispatcher))
    registry.register(EditTool(allowed_dir=allowed_dir, dispatcher=dispatcher))
    registry.register(GrepTool(working_dir=tool_workspace, allowed_dir=allowed_dir))
    registry.register(GlobTool(working_dir=tool_workspace, allowed_dir=allowed_dir))
    registry.register(BashTool(
        working_dir=tool_workspace,
        timeout_ms=exec_timeout * 1000,
        restrict_to_workspace=restrict_to_workspace,
        dispatcher=dispatcher,
    ))
    registry.register(WebSearchTool(
        tavily_api_key=tavily_api_key,
        brave_api_key=brave_api_key,
    ))
    registry.register(WebFetchTool())

    if subagent_executor is not None and profile == "main":
        registry.register(AgentTool(executor=subagent_executor))

    if cron_service is not None and profile == "main":
        cron_tool = CronTool(cron_service)
        if origin_channel and origin_chat_id:
            cron_tool.set_context(origin_channel, origin_chat_id)
        registry.register(cron_tool)

    register_task_tools(
        registry,
        task_mode=task_mode,
        plan_manager=plan_manager,
        task_session_key=task_session_key or thread_id,
        task_base_dir=task_base_dir,
    )

    if engine is not None:
        from auraeve.agent.engines.vector.engine import VectorContextEngine
        if isinstance(engine, VectorContextEngine):
            from auraeve.agent.tools.memory_search import MemorySearchTool
            from auraeve.agent.tools.memory_get import MemoryGetTool
            from auraeve.agent.tools.memory_status import MemoryStatusTool
            registry.register(MemorySearchTool(
                manager=engine.memory_manager,
                search_limit=engine.search_limit,
            ))
            registry.register(MemoryGetTool(manager=engine.memory_manager))
            registry.register(MemoryStatusTool(manager=engine.memory_manager))

    return registry
