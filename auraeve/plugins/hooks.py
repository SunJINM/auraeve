"""HookRunner：执行插件生命周期钩子。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from .base import (
        Plugin,
        HookAfterToolCallEvent,
        HookBeforeModelResolveEvent,
        HookBeforeModelResolveResult,
        HookBeforePromptBuildEvent,
        HookBeforePromptBuildResult,
        HookBeforeToolCallEvent,
        HookBeforeToolCallResult,
        HookMessageSendingEvent,
        HookMessageSendingResult,
        HookSessionEvent,
    )


class HookRunner:
    """
    执行所有已注册插件的生命周期钩子。

    钩子分两类：
    - Void（fire-and-forget）：并行执行，错误只记录不中断
      after_tool_call, session_start, session_end
    - Modifying（顺序执行，结果合并）：
      before_prompt_build, before_tool_call, message_sending, before_model_resolve
    """

    def __init__(self, plugins: list["Plugin"]) -> None:
        self._plugins = plugins

    # ── Modifying Hooks ───────────────────────────────────────────────────────

    async def run_before_prompt_build(
        self, event: "HookBeforePromptBuildEvent"
    ) -> "HookBeforePromptBuildResult":
        from .base import HookBeforePromptBuildResult

        prepend_parts: list[str] = []
        append_parts: list[str] = []

        for plugin in self._plugins:
            try:
                result = await plugin.before_prompt_build(event)
                if result:
                    if result.prepend_context:
                        prepend_parts.append(result.prepend_context.strip())
                    if result.append_context:
                        append_parts.append(result.append_context.strip())
            except Exception as e:
                logger.error(f"[hooks] {plugin.id}.before_prompt_build 失败: {e}")

        return HookBeforePromptBuildResult(
            prepend_context="\n\n".join(prepend_parts) if prepend_parts else None,
            append_context="\n\n".join(append_parts) if append_parts else None,
        )

    async def run_before_tool_call(
        self, event: "HookBeforeToolCallEvent"
    ) -> "HookBeforeToolCallResult":
        from .base import HookBeforeToolCallResult

        current_params = event.params

        for plugin in self._plugins:
            try:
                result = await plugin.before_tool_call(event)
                if result:
                    if result.block:
                        logger.info(
                            f"[hooks] {plugin.id} 阻止了工具调用 {event.tool_name}: {result.block_reason}"
                        )
                        return result
                    if result.params is not None:
                        current_params = result.params
                        # 更新 event.params 供下一个插件看到修改后的参数
                        event = type(event)(
                            tool_name=event.tool_name,
                            params=current_params,
                            session_id=event.session_id,
                            channel=event.channel,
                            chat_id=event.chat_id,
                        )
            except Exception as e:
                logger.error(f"[hooks] {plugin.id}.before_tool_call 失败: {e}")

        return HookBeforeToolCallResult(params=current_params)

    async def run_message_sending(
        self, event: "HookMessageSendingEvent"
    ) -> "HookMessageSendingResult":
        from .base import HookMessageSendingResult

        current_content = event.content

        for plugin in self._plugins:
            try:
                result = await plugin.message_sending(event)
                if result:
                    if result.cancel:
                        logger.info(f"[hooks] {plugin.id} 取消了消息发送")
                        return result
                    if result.content is not None:
                        current_content = result.content
                        event = type(event)(
                            content=current_content,
                            channel=event.channel,
                            chat_id=event.chat_id,
                            session_id=event.session_id,
                            metadata=event.metadata,
                        )
            except Exception as e:
                logger.error(f"[hooks] {plugin.id}.message_sending 失败: {e}")

        return HookMessageSendingResult(content=current_content)

    async def run_before_model_resolve(
        self, event: "HookBeforeModelResolveEvent"
    ) -> str | None:
        """返回第一个插件提供的 model override（高优先级插件优先）。"""
        for plugin in self._plugins:
            try:
                result = await plugin.before_model_resolve(event)
                if result and result.model_override:
                    logger.info(
                        f"[hooks] {plugin.id} 将模型覆盖为 {result.model_override}"
                    )
                    return result.model_override
            except Exception as e:
                logger.error(f"[hooks] {plugin.id}.before_model_resolve 失败: {e}")

        return None

    # ── Void Hooks（并行，fire-and-forget）─────────────────────────────────────

    async def run_after_tool_call(self, event: "HookAfterToolCallEvent") -> None:
        await self._run_void("after_tool_call", event)

    async def run_session_start(self, event: "HookSessionEvent") -> None:
        await self._run_void("session_start", event)

    async def run_session_end(self, event: "HookSessionEvent") -> None:
        await self._run_void("session_end", event)

    async def _run_void(self, hook_name: str, event: object) -> None:
        async def _call(plugin: "Plugin"):
            try:
                await getattr(plugin, hook_name)(event)
            except Exception as e:
                logger.error(f"[hooks] {plugin.id}.{hook_name} 失败: {e}")

        await asyncio.gather(*[_call(p) for p in self._plugins])
