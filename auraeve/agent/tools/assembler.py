from __future__ import annotations

from pathlib import Path

from auraeve.agent.tools.cron import CronTool
from auraeve.agent.tools.filesystem import EditTool, ReadTool, WriteTool
from auraeve.agent.tools.search import GlobTool, GrepTool
from auraeve.agent.tools.registry import ToolRegistry
from auraeve.agent.tools.shell import BashTool
from auraeve.agent.tools.agent_tool import AgentTool
from auraeve.agent.tools.image_generation import ImageGenerationTool
from auraeve.agent.tools.web import WebFetchTool, WebSearchTool
from auraeve.execution.dispatcher import ExecutionDispatcher


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
    channel_users: dict[str, str] | None = None,
    notify_channel: str = "",
    subagent_executor=None,
    cron_service=None,
    origin_channel: str | None = None,
    origin_chat_id: str | None = None,
    thread_id: str | None = None,
    execution_workspace: str | None = None,
    execution_dispatcher: ExecutionDispatcher | None = None,
    task_session_key: str | None = None,
    task_base_dir: Path | None = None,
    image_model: str = "gpt-image-2",
) -> ToolRegistry:
    del task_session_key, task_base_dir
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

    image_api_key = str(getattr(provider, "api_key", "") or "")
    if image_api_key:
        registry.register(ImageGenerationTool(
            api_key=image_api_key,
            api_base=getattr(provider, "api_base", None),
            image_model=image_model,
        ))

    if subagent_executor is not None and profile == "main":
        registry.register(AgentTool(executor=subagent_executor))

    if cron_service is not None and profile == "main":
        cron_tool = CronTool(cron_service)
        if origin_channel and origin_chat_id:
            cron_tool.set_context(origin_channel, origin_chat_id)
        registry.register(cron_tool)

    return registry
