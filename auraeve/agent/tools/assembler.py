from __future__ import annotations

from pathlib import Path

from auraeve.agent.tools.browser import BrowserTool
from auraeve.agent.tools.cron import CronTool
from auraeve.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from auraeve.agent.tools.message import MessageTool
from auraeve.agent.tools.media_understand import MediaUnderstandTool
from auraeve.agent.tools.pdf import PdfTool
from auraeve.agent.tools.plan import TodoTool
from auraeve.agent.tools.registry import ToolRegistry
from auraeve.agent.tools.shell import ExecTool
from auraeve.agent.tools.spawn import SpawnTool
from auraeve.agent.tools.web import WebFetchTool, WebSearchTool
from auraeve.execution.dispatcher import ExecutionDispatcher


def build_tool_registry(
    *,
    profile: str,
    workspace: Path,
    restrict_to_workspace: bool,
    exec_timeout: int,
    brave_api_key: str | None,
    bus_publish_outbound,
    provider,
    model: str,
    plan_manager,
    channel_users: dict[str, str] | None = None,
    notify_channel: str = "",
    spawn_manager=None,
    cron_service=None,
    origin_channel: str | None = None,
    origin_chat_id: str | None = None,
    thread_id: str | None = None,
    engine=None,
    execution_workspace: str | None = None,
    execution_dispatcher: ExecutionDispatcher | None = None,
    media_runtime=None,
) -> ToolRegistry:
    registry = ToolRegistry()
    tool_workspace = execution_workspace or str(workspace)
    dispatcher = execution_dispatcher or ExecutionDispatcher()
    allowed_dir = None
    if restrict_to_workspace:
        allowed_dir = Path(tool_workspace)

    registry.register(
        ReadFileTool(allowed_dir=allowed_dir, dispatcher=dispatcher)
    )
    registry.register(
        WriteFileTool(allowed_dir=allowed_dir, dispatcher=dispatcher)
    )
    registry.register(
        EditFileTool(allowed_dir=allowed_dir, dispatcher=dispatcher)
    )
    registry.register(
        ListDirTool(allowed_dir=allowed_dir, dispatcher=dispatcher)
    )
    registry.register(ExecTool(
        working_dir=tool_workspace,
        timeout=exec_timeout,
        restrict_to_workspace=restrict_to_workspace,
        dispatcher=dispatcher,
    ))
    registry.register(WebSearchTool(api_key=brave_api_key))
    registry.register(WebFetchTool())

    message_tool = MessageTool(
        send_callback=bus_publish_outbound,
        channel_users=channel_users or {},
        notify_channel=notify_channel,
    )
    if origin_channel and origin_chat_id:
        message_tool.set_context(origin_channel, origin_chat_id)
    registry.register(message_tool)
    if media_runtime is not None:
        registry.register(MediaUnderstandTool(media_runtime))

    if spawn_manager is not None:
        registry.register(SpawnTool(manager=spawn_manager))

    if cron_service is not None and profile == "main":
        cron_tool = CronTool(cron_service)
        if origin_channel and origin_chat_id:
            cron_tool.set_context(origin_channel, origin_chat_id)
        registry.register(cron_tool)

    todo_tool = TodoTool(plan_manager=plan_manager)
    if thread_id:
        todo_tool.set_thread_id(thread_id)
    registry.register(todo_tool)

    registry.register(BrowserTool())
    registry.register(PdfTool(provider=provider, model=model))

    if engine is not None:
        from auraeve.agent.engines.vector.engine import VectorContextEngine
        if isinstance(engine, VectorContextEngine):
            from auraeve.agent.tools.memory_search import MemorySearchTool
            registry.register(MemorySearchTool(
                store=engine.store,
                embedder=engine.embedder,
                search_limit=engine.search_limit,
                vector_weight=engine.vector_weight,
                text_weight=engine.text_weight,
                mmr_lambda=engine.mmr_lambda,
                half_life_days=engine.half_life_days,
            ))

    return registry
