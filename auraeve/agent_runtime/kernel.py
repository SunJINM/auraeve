"""运行时内核协调器。

- PromptAssembler 负责提示词组装（支持 `before_prompt_build` 钩子）
- SessionAttemptRunner + RunOrchestrator 共享执行内核
- ToolPolicyEngine 负责分层工具策略判定
- SubagentExecutor 负责子体执行与生命周期管理
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from auraeve.agent_runtime.command_projection import project_command_to_messages
from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.agent_runtime.command_types import QueuedCommand
from auraeve.agent_runtime.runtime_scheduler import RuntimeScheduler
from auraeve.bus.events import OutboundMessage
from auraeve.bus.queue import OutboundDispatcher
from auraeve.llm.model_registry import ModelRegistry
from auraeve.providers.base import LLMProvider
from auraeve.agent.tools.registry import ToolRegistry
from auraeve.agent.tools.agent_tool import AgentTool
from auraeve.agent.tools.cron import CronTool
from auraeve.agent.tools.assembler import build_tool_registry, register_task_tools
from auraeve.agent.context import ContextBuilder, SILENT_REPLY_TOKEN, HEARTBEAT_OK
from auraeve.session.manager import SessionManager
from auraeve.mcp import MCPRuntimeManager

from .prompt.assembler import PromptAssembler
from .session_attempt import SessionAttemptRunner
from .run_orchestrator import RunOrchestrator
from .task_reminders import build_task_runtime_instruction
from .tool_policy.engine import ToolPolicyEngine

if TYPE_CHECKING:
    from auraeve.cron.service import CronService
    from auraeve.memory_lifecycle import MemoryLifecycleService


def _force_unlimited_main_budget(raw: dict | None) -> dict:
    """主智能体固定不设执行预算上限（面向长时运行）。

    强制把轮数 / 工具调用次数 / 墙钟时间上限写死为 0（= 不限制），
    无视配置文件里的历史值；上下文增长改由主动压缩 + 工具结果清理控制。
    子体在 react_loop 中各自构造 runner 并带步数上限，不受此影响。
    """
    base = dict(raw or {})
    base.update(
        {
            "maxTurns": 0,
            "maxToolCallsTotal": 0,
            "maxToolCallsPerTurn": 0,
            "maxWallTimeMs": 0,
        }
    )
    return base


class RuntimeKernel:
    """Runtime kernel main entry."""

    UNEXPECTED_SILENT_FALLBACK = "我这边没有生成可发送的回复，请再试一次。"

    def __init__(
        self,
        bus: OutboundDispatcher,
        provider: LLMProvider,
        workspace: Path,
        sessions_dir: Path,
        memory_window: int = 50,
        model: str | None = None,
        max_iterations: int = 100,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        brave_api_key: str | None = None,
        tavily_api_key: str | None = None,
        exec_timeout: int = 60,
        restrict_to_workspace: bool = False,
        mcp_config: dict | None = None,
        cron_service: "CronService | None" = None,
        channel_users: dict[str, str] | None = None,
        notify_channel: str = "",
        thinking_budget_tokens: int | None = None,
        token_budget: int = 120_000,
        global_deny_tools: set[str] | None = None,
        session_tool_policy: dict | None = None,
        max_global_subagent_concurrent: int = 10,
        max_session_subagent_concurrent: int = 8,
        execution_workspace: str | None = None,
        runtime_execution: dict | None = None,
        runtime_loop_guard: dict | None = None,
        memory_lifecycle: "MemoryLifecycleService | None" = None,
    ) -> None:
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.brave_api_key = brave_api_key
        self.tavily_api_key = tavily_api_key
        self.exec_timeout = exec_timeout
        self.restrict_to_workspace = restrict_to_workspace
        self.thinking_budget_tokens = thinking_budget_tokens
        self.cron_service = cron_service
        self._channel_users = channel_users or {}
        self._notify_channel = notify_channel
        self._execution_workspace = execution_workspace
        self.memory_lifecycle = memory_lifecycle
        self._reload_lock = asyncio.Lock()

        # 会话管理与任务存储
        self.sessions = SessionManager(sessions_dir)
        self._task_base_dir = sessions_dir.parent / "tasks"

        # Tool registry (main agent).
        self.tools = ToolRegistry()

        # Policy engine (main agent).
        self.policy = ToolPolicyEngine(
            is_subagent=False,
            global_deny=global_deny_tools,
            session_policy=session_tool_policy,
        )

        # Prompt 组装器（含 token 预算报告）
        self.assembler = PromptAssembler(
            workspace=workspace,
            memory_window=memory_window,
            execution_workspace=execution_workspace,
            token_budget=token_budget,
        )
        self._initialize_command_runtime()

        # 子体执行系统
        from auraeve.subagents.data.repositories import SubagentStore
        from auraeve.subagents.executor import SubagentExecutor

        subagent_db_path = sessions_dir / "subagents.db" if sessions_dir else workspace / "subagents.db"
        subagent_db_path.parent.mkdir(parents=True, exist_ok=True)
        self._subagent_store = SubagentStore(str(subagent_db_path))
        self._subagent_executor = SubagentExecutor(
            store=self._subagent_store,
            command_queue=self.command_queue,
            provider=provider,
            tool_builder=lambda task: build_tool_registry(
                profile="main" if task.agent_type == "coordinator" else "subagent",
                workspace=self.workspace,
                restrict_to_workspace=self.restrict_to_workspace,
                exec_timeout=self.exec_timeout,
                brave_api_key=self.brave_api_key,
                tavily_api_key=self.tavily_api_key,
                bus_publish_outbound=self.bus.publish_outbound,
                provider=self.provider,
                model=self.model,
                channel_users=self._channel_users,
                notify_channel=self._notify_channel,
                subagent_executor=self._subagent_executor,
                cron_service=self.cron_service,
                origin_channel=task.origin_channel or None,
                origin_chat_id=task.origin_chat_id or None,
                thread_id=f"sub:{task.task_id}",
                execution_workspace=task.worktree_path or self._execution_workspace,
                task_base_dir=self._task_base_dir,
            ),
            policy=self.policy,
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_iterations=50,
            thinking_budget_tokens=thinking_budget_tokens or 0,
            prompt_assembler=self.assembler,
            max_concurrent=max_global_subagent_concurrent,
            workspace=str(workspace),
            sessions_dir=sessions_dir / "subagent_sessions",
        )

        # 主执行器与统一运行编排器
        self._runner = SessionAttemptRunner(
            provider=provider,
            tools=self.tools,
            policy=self.policy,
            checkpoint_drain=self._drain_checkpoint_messages,
            max_iterations=max_iterations,
            thinking_budget_tokens=thinking_budget_tokens,
            runtime_execution=_force_unlimited_main_budget(runtime_execution),
            runtime_loop_guard=runtime_loop_guard,
            token_budget=token_budget,
        )
        self._orchestrator = RunOrchestrator(
            runner=self._runner,
            provider=provider,
            max_retries=8,
            is_subagent=False,
            token_budget=token_budget,
        )

        self._register_default_tools()
        self._mcp_runtime = MCPRuntimeManager(self.tools, mcp_config or {})

    # Public API

    def register_tool(self, tool) -> None:
        self.tools.register(tool)

    def _initialize_command_runtime(self) -> None:
        self.command_queue = RuntimeCommandQueue()
        self.scheduler = RuntimeScheduler(
            queue=self.command_queue,
            run_command=self.execute_command,
        )

    def stop(self) -> None:
        logger.info("运行内核正在停止")

    async def close_mcp(self) -> None:
        await self._mcp_runtime.stop()

    def get_mcp_status(self) -> dict:
        return self._mcp_runtime.status()

    def get_mcp_events(self) -> list[dict]:
        return self._mcp_runtime.events()

    async def reconnect_mcp_server(self, server_id: str) -> dict:
        return await self._mcp_runtime.reconnect(server_id)

    def command_factory(self, **kwargs) -> QueuedCommand:
        return QueuedCommand(**kwargs)

    async def execute_command(
        self,
        command: QueuedCommand,
    ):
        await self._mcp_runtime.start()
        projected_messages = project_command_to_messages(command)
        response = await self._process_projected_command(command, projected_messages)
        if isinstance(response, OutboundMessage) and hasattr(self, "bus") and self.bus is not None:
            await self._publish_command_response(command, response)
        return response

    async def _process_projected_command(
        self,
        command: QueuedCommand,
        projected_messages: list[dict],
    ):
        payload = command.payload
        channel, chat_id = self._derive_channel_and_chat_id(command)
        content = "\n\n".join(
            str(msg.get("content", ""))
            for msg in projected_messages
            if str(msg.get("content", ""))
        )
        metadata = dict(payload.get("metadata") or {})
        metadata.setdefault("command_mode", command.mode)
        metadata.setdefault("command_origin", command.origin)
        if command.mode == "task-notification":
            metadata.setdefault("is_meta_event", True)
            metadata.setdefault("meta_event_kind", "task-notification")
        return await self._process_message(
            session_key=command.session_key,
            channel=channel,
            sender_id=str(payload.get("sender_id", command.source or "system")),
            chat_id=chat_id,
            content=content,
            media=list(payload.get("media") or []),
            attachments=list(payload.get("attachments") or []),
            metadata=metadata,
        )

    @staticmethod
    def _derive_channel_and_chat_id(command: QueuedCommand) -> tuple[str, str]:
        payload = command.payload
        channel = str(payload.get("channel") or command.source or "system")
        chat_id = str(payload.get("chat_id") or "")
        if chat_id:
            return channel, chat_id
        if ":" in command.session_key:
            prefix, suffix = command.session_key.split(":", 1)
            return channel or prefix, suffix
        return channel, command.session_key

    async def _publish_command_response(
        self,
        command: QueuedCommand,
        response: OutboundMessage,
    ) -> None:
        if command.mode == "cron":
            deliver_channel = str(command.payload.get("deliver_channel") or "")
            deliver_to = str(command.payload.get("deliver_to") or "")
            if deliver_channel and deliver_to:
                await self.bus.publish_outbound(
                    OutboundMessage(
                        channel=deliver_channel,
                        chat_id=deliver_to,
                        content=response.content,
                    )
                )
                return
        if response.channel:
            await self.bus.publish_outbound(response)

    def _drain_checkpoint_messages(
        self,
        *,
        thread_id: str,
        is_subagent: bool,
    ) -> list[dict]:
        commands = self.scheduler.snapshot_for_checkpoint(
            agent_id=thread_id if is_subagent else None,
            is_main_thread=not is_subagent,
            max_priority="next",
            session_key=thread_id,
        )
        if not commands:
            return []
        messages: list[dict] = []
        for command in commands:
            messages.extend(project_command_to_messages(command))
        self.command_queue.remove_commands(commands)
        return messages

    # Tool initialization

    def _register_default_tools(self) -> None:
        self.tools = build_tool_registry(
            profile="main",
            workspace=self.workspace,
            restrict_to_workspace=self.restrict_to_workspace,
            exec_timeout=self.exec_timeout,
            brave_api_key=self.brave_api_key,
            tavily_api_key=self.tavily_api_key,
            bus_publish_outbound=self.bus.publish_outbound,
            provider=self.provider,
            model=self.model,
            channel_users=self._channel_users,
            notify_channel=self._notify_channel,
            subagent_executor=self._subagent_executor,
            cron_service=self.cron_service,
            execution_workspace=self._execution_workspace,
            task_base_dir=self._task_base_dir,
        )
        self._runner._tools = self.tools

    async def reload_runtime_config(self, new_config: dict) -> dict[str, list]:
        applied: list[str] = []
        requires_restart: list[str] = []
        issues: list[dict[str, str]] = []

        async with self._reload_lock:
            if "LLM_TEMPERATURE" in new_config:
                self.temperature = float(new_config["LLM_TEMPERATURE"])
                applied.append("LLM_TEMPERATURE")
            if "LLM_MAX_TOKENS" in new_config:
                self.max_tokens = int(new_config["LLM_MAX_TOKENS"])
                applied.append("LLM_MAX_TOKENS")
            if "LLM_MAX_TOOL_ITERATIONS" in new_config:
                self.max_iterations = int(new_config["LLM_MAX_TOOL_ITERATIONS"])
                self._runner.apply_runtime_controls(max_iterations=self.max_iterations)
                applied.append("LLM_MAX_TOOL_ITERATIONS")
            if "RUNTIME_LOOP_GUARD" in new_config:
                self._runner.apply_runtime_controls(runtime_loop_guard=new_config["RUNTIME_LOOP_GUARD"])
                applied.append("RUNTIME_LOOP_GUARD")
            if "LLM_MEMORY_WINDOW" in new_config:
                self.assembler.apply_runtime_controls(memory_window=int(new_config["LLM_MEMORY_WINDOW"]))
                applied.append("LLM_MEMORY_WINDOW")
            if "GLOBAL_DENY_TOOLS" in new_config:
                self.policy.apply_runtime_policy(global_deny=new_config.get("GLOBAL_DENY_TOOLS") or [])
                applied.append("GLOBAL_DENY_TOOLS")
            if "SESSION_TOOL_POLICY" in new_config:
                self.policy.apply_runtime_policy(session_policy=new_config.get("SESSION_TOOL_POLICY") or {})
                applied.append("SESSION_TOOL_POLICY")

            if "LLM_MODELS" in new_config:
                try:
                    self._reload_primary_model(list(new_config.get("LLM_MODELS") or []))
                    applied.append("LLM_MODELS")
                except Exception as e:
                    issues.append({"code": "llm_models_reload_failed", "message": str(e)})
                    requires_restart.append("LLM_MODELS")

            if "MCP" in new_config:
                try:
                    result = await self._mcp_runtime.reload(new_config.get("MCP") or {})
                    applied.extend(result.get("applied") or ["MCP"])
                    requires_restart.extend(result.get("requiresRestart") or [])
                    issues.extend(result.get("issues") or [])
                except Exception as e:
                    issues.append({"code": "mcp_reload_failed", "message": str(e)})
                    requires_restart.append("MCP")

            if "TOKEN_BUDGET" in new_config:
                budget = int(new_config["TOKEN_BUDGET"])
                self.assembler.apply_runtime_controls(token_budget=budget)
                self._runner.apply_runtime_controls(token_budget=budget)
                self._orchestrator.apply_runtime_controls(token_budget=budget)
                applied.append("TOKEN_BUDGET")

        return {
            "applied": applied,
            "requiresRestart": sorted(set(requires_restart)),
            "issues": issues,
        }

    def _reload_primary_model(self, raw_models: list[dict]) -> None:
        from auraeve.providers.openai_provider import build_openai_provider_from_model_card

        primary = ModelRegistry(raw_models).primary()
        primary_raw = next(
            item
            for item in raw_models
            if isinstance(item, dict) and str(item.get("id") or "") == primary.id
        )
        provider = build_openai_provider_from_model_card(primary_raw)

        self.provider = provider
        self.model = primary.model
        self.temperature = primary.temperature
        self.max_tokens = max(1, primary.max_tokens)
        self.thinking_budget_tokens = primary.thinking_budget_tokens or None

        self._runner._provider = provider
        self._runner._thinking_budget_tokens = self.thinking_budget_tokens
        self._orchestrator._provider = provider

        if hasattr(self, "_subagent_executor"):
            self._subagent_executor._provider = provider
            self._subagent_executor._model = self.model
            self._subagent_executor._temperature = self.temperature
            self._subagent_executor._max_tokens = self.max_tokens
            self._subagent_executor._thinking_budget_tokens = self.thinking_budget_tokens or 0

        self._register_default_tools()

    def _set_tool_context(self, tools: ToolRegistry, channel: str, chat_id: str, thread_id: str) -> None:
        agent_tool = tools.get("agent")
        if agent_tool is not None and isinstance(agent_tool, AgentTool):
            agent_tool.set_context(
                channel,
                chat_id,
                thread_id,
                session_history_loader=lambda tid=thread_id: self.sessions.get_or_create(tid).get_history(),
            )
        cron_tool = tools.get("cron")
        if cron_tool is not None and isinstance(cron_tool, CronTool):
            cron_tool.set_context(channel, chat_id)
    def _resolve_runtime_tools(self, channel: str, chat_id: str, thread_id: str) -> ToolRegistry:
        base_tools = getattr(self, "tools", None)
        registry = base_tools.clone() if isinstance(base_tools, ToolRegistry) else ToolRegistry()
        register_task_tools(
            registry,
            task_session_key=thread_id,
            task_base_dir=getattr(self, "_task_base_dir", None),
        )
        self._set_tool_context(registry, channel, chat_id, thread_id)
        return registry

    def _persist_tool_transcript(self, session, transcript_messages: list[dict]) -> None:
        for message in transcript_messages:
            role = message.get("role")
            if role not in {"assistant", "tool"}:
                continue
            payload = {k: v for k, v in message.items() if k != "role"}
            session.add_message(role, payload.pop("content", ""), **payload)

    async def _extract_attachments_legacy(self, attachments):
        if not attachments:
            return None
        from auraeve.agent.media import download_and_extract

        extracted = []
        for att in attachments:
            if not att.url:
                continue
            result = await download_and_extract(
                url=att.url,
                workspace=self.workspace,
                original_filename=att.filename,
            )
            extracted.append(result)
        return extracted or None

    @staticmethod
    def _sanitize_assistant_output(content: str | None) -> str | None:
        """Sanitize control tokens from assistant output.

        Rules:
        - exact control token reply -> silent (return None)
        - mixed content + control token lines -> drop control lines, keep text
        - empty/blank output -> silent
        """
        if content is None:
            return None

        text = str(content).replace("\r\n", "\n")
        text = text.strip().strip('"').strip("'").strip()
        if not text:
            return None
        if text in {SILENT_REPLY_TOKEN, HEARTBEAT_OK}:
            return None

        lines = [line for line in text.split("\n") if line.strip() not in {SILENT_REPLY_TOKEN, HEARTBEAT_OK}]
        cleaned = "\n".join(lines).strip()
        return cleaned or None

    # Message processing

    async def _process_message(
        self,
        *,
        session_key: str,
        channel: str,
        sender_id: str,
        chat_id: str,
        content: str,
        media: list[str] | None = None,
        attachments=None,
        metadata: dict | None = None,
    ) -> OutboundMessage | None:
        metadata = dict(metadata or {})
        is_meta_event = bool(metadata.get("is_meta_event"))
        media = list(media or [])
        attachments = list(attachments or [])

        logger.bind(
            sessionKey=session_key,
            channel=channel,
            senderId=sender_id,
            contentLength=len(content),
            contentPreview=self._log_preview(content, 80),
        ).debug("收到用户消息，开始处理")

        key = session_key
        session = self.sessions.get_or_create(key)
        thread_id = key

        cmd = content.strip().lower()
        if cmd == "/new":
            session.clear()
            self.sessions.save(session)
            self.sessions.invalidate(session.key)
            return OutboundMessage(
                channel=channel,
                chat_id=chat_id,
                content="新会话已开始。",
            )
        if cmd == "/help":
            return OutboundMessage(
                channel=channel,
                chat_id=chat_id,
                content="可用命令：\n/new - 开始新对话\n/help - 显示帮助",
            )

        runtime_tools = self._resolve_runtime_tools(channel, chat_id, thread_id)

        current_message = content

        extracted_attachments = await self._extract_attachments_legacy(attachments)

        # PromptAssembler
        runtime_instruction = build_task_runtime_instruction(
            session_key=session.key,
            session_messages=session.messages,
            available_tools=set(runtime_tools.tool_names),
            task_base_dir=getattr(self, "_task_base_dir", None),
        )
        assemble_result = await self.assembler.assemble(
            session_id=session.key,
            messages=session.get_history(),
            current_query=current_message,
            channel=channel,
            chat_id=chat_id,
            media=media if media else None,
            attachments=extracted_attachments,
            available_tools=set(runtime_tools.tool_names),
            runtime_instruction=runtime_instruction or "",
        )
        # 通过统一编排器执行（含恢复策略）
        recovery_result = await self._orchestrator.run(
            messages=assemble_result.messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            tools=runtime_tools,
            thread_id=thread_id,
            channel=channel,
            chat_id=chat_id,
        )

        final_content = recovery_result.final_content
        tools_used = recovery_result.tools_used
        final_images = getattr(recovery_result, "final_images", None)
        if not isinstance(final_images, list):
            final_images = []

        if recovery_result.recovery_actions:
            logger.debug(f"模型恢复动作：{recovery_result.recovery_actions}")

        command_mode = str(metadata.get("command_mode") or "prompt")
        allow_silent_response = is_meta_event or command_mode in {"heartbeat", "cron", "task-notification"}
        sanitized_content = self._sanitize_assistant_output(final_content)
        if sanitized_content is None and not allow_silent_response:
            logger.warning(
                "模型返回了空回复，已使用兜底文案；"
                f"command_mode={command_mode} "
                f"is_meta_event={is_meta_event} "
                f"rawLength={len(str(final_content or ''))}"
            )
            sanitized_content = self.UNEXPECTED_SILENT_FALLBACK
        persist_content = sanitized_content if sanitized_content is not None else SILENT_REPLY_TOKEN

        should_generate_title = (
            not is_meta_event
            and not str((session.metadata or {}).get("title") or "").strip()
            and not any(msg.get("role") == "user" for msg in session.messages)
        )
        if should_generate_title:
            generated_title = await self._generate_session_title(content)
            if generated_title:
                session.metadata["title"] = generated_title

        if not is_meta_event:
            session.add_message(
                "user",
                content,
                channel=channel,
                chat_id=chat_id,
                sender_id=sender_id,
            )
        self._persist_tool_transcript(session, recovery_result.messages)
        session.add_message("assistant", persist_content,
                            tools_used=tools_used if tools_used else None,
                            images=final_images if final_images else None)
        self.sessions.save(session)

        if self.memory_lifecycle is not None and not is_meta_event:
            asyncio.create_task(
                self.memory_lifecycle.record_turn(
                    session_key=session.key,
                    channel=channel,
                    chat_id=chat_id,
                    user_content=content,
                    assistant_content=sanitized_content or "",
                    tools_used=tools_used if tools_used else [],
                )
            )

        # Silent token handling
        if sanitized_content is None:
            logger.debug(
                "检测到静默回复，跳过对外发送；"
                f"command_mode={command_mode} "
                f"is_meta_event={is_meta_event}"
            )
            return None
        final_content = sanitized_content

        logger.bind(
            sessionKey=session_key,
            channel=channel,
            senderId=sender_id,
            contentLength=len(final_content),
            contentPreview=self._log_preview(final_content, 120),
        ).debug("助手回复已生成")

        return OutboundMessage(
            channel=channel,
            chat_id=chat_id,
            content=final_content,
            metadata=metadata,
        )

    @staticmethod
    def _log_preview(content: str | None, limit: int = 120) -> str:
        text = str(content or "").replace("\r", " ").replace("\n", " ").strip()
        if len(text) <= limit:
            return text
        return f"{text[:limit]}…"

    async def _generate_session_title(self, user_content: str) -> str:
        prompt = str(user_content or "").strip()
        if not prompt:
            return ""
        try:
            response = await self.provider.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是会话标题生成器。根据用户第一句话生成一个简短中文标题，"
                            "不超过12个汉字，不要引号，不要句号，不要解释。"
                        ),
                    },
                    {"role": "user", "content": prompt[:1000]},
                ],
                tools=None,
                model=self.model,
                max_tokens=32,
                temperature=0.2,
            )
            title = str(response.content or "").strip()
        except Exception as exc:
            logger.debug(f"生成会话标题失败：{exc}")
            return ""
        title = title.strip().strip('"').strip("'").strip("“”‘’`").strip()
        for sep in ("\n", "\r", "。", "：", ":", " - ", "—"):
            if sep in title:
                title = title.split(sep, 1)[0].strip()
        title = " ".join(title.split())
        return title[:24]
