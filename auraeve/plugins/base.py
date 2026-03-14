"""Plugin Hook 数据类与 Plugin 基类。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── 事件数据类 ────────────────────────────────────────────────────────────────

@dataclass
class HookBeforePromptBuildEvent:
    """before_prompt_build：构建系统提示词之前触发。"""
    session_id: str
    channel: str | None
    chat_id: str | None
    current_query: str


@dataclass
class HookBeforePromptBuildResult:
    """before_prompt_build 钩子返回结果，可注入上下文到系统提示词。"""
    prepend_context: str | None = None   # 追加到系统提示词末尾（前缀）
    append_context: str | None = None    # 追加到系统提示词末尾（后缀）


@dataclass
class HookBeforeToolCallEvent:
    """before_tool_call：工具调用执行之前触发。"""
    tool_name: str
    params: dict[str, Any]
    session_id: str
    channel: str | None = None
    chat_id: str | None = None


@dataclass
class HookBeforeToolCallResult:
    """before_tool_call 钩子返回结果。"""
    params: dict[str, Any] | None = None   # 替换参数（None = 不修改）
    block: bool = False                     # 阻止工具调用
    block_reason: str | None = None         # 阻止原因（作为工具结果返回）


@dataclass
class HookAfterToolCallEvent:
    """after_tool_call：工具调用完成之后触发（fire-and-forget）。"""
    tool_name: str
    params: dict[str, Any]
    result: str
    session_id: str
    channel: str | None = None
    chat_id: str | None = None
    error: str | None = None               # 若执行出错，错误信息


@dataclass
class HookMessageSendingEvent:
    """message_sending：向用户发送消息之前触发。"""
    content: str
    channel: str
    chat_id: str
    session_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HookMessageSendingResult:
    """message_sending 钩子返回结果。"""
    content: str | None = None   # 替换消息内容（None = 不修改）
    cancel: bool = False          # 取消发送


@dataclass
class HookBeforeModelResolveEvent:
    """before_model_resolve：确定使用哪个模型之前触发。"""
    current_query: str
    session_id: str
    default_model: str
    channel: str | None = None
    chat_id: str | None = None


@dataclass
class HookBeforeModelResolveResult:
    """before_model_resolve 钩子返回结果。"""
    model_override: str | None = None    # 覆盖模型名称


@dataclass
class HookSessionEvent:
    """会话开始/结束事件。"""
    session_id: str
    channel: str | None = None
    chat_id: str | None = None


# ── Plugin 基类 ───────────────────────────────────────────────────────────────

class Plugin:
    """
    插件基类。

    所有方法均为可选覆盖。继承此类并实现需要的钩子方法即可。

    示例（注入天气信息到系统提示词）：
        class WeatherPlugin(Plugin):
            @property
            def id(self) -> str:
                return "weather"

            async def before_prompt_build(self, event):
                weather = await fetch_weather()
                return HookBeforePromptBuildResult(
                    append_context=f"\\n## 当前天气\\n{weather}"
                )
    """

    @property
    def id(self) -> str:
        return self.__class__.__name__

    async def before_prompt_build(
        self, event: HookBeforePromptBuildEvent
    ) -> HookBeforePromptBuildResult | None:
        """在系统提示词构建之前调用，可注入额外上下文。"""
        return None

    async def before_tool_call(
        self, event: HookBeforeToolCallEvent
    ) -> HookBeforeToolCallResult | None:
        """在工具调用执行之前调用，可修改参数或阻止调用。"""
        return None

    async def after_tool_call(self, event: HookAfterToolCallEvent) -> None:
        """工具调用完成后调用（fire-and-forget，不影响结果）。"""
        pass

    async def message_sending(
        self, event: HookMessageSendingEvent
    ) -> HookMessageSendingResult | None:
        """向用户发送消息之前调用，可修改内容或取消发送。"""
        return None

    async def before_model_resolve(
        self, event: HookBeforeModelResolveEvent
    ) -> HookBeforeModelResolveResult | None:
        """确定模型之前调用，可覆盖模型选择。"""
        return None

    async def session_start(self, event: HookSessionEvent) -> None:
        """会话开始时调用（fire-and-forget）。"""
        pass

    async def session_end(self, event: HookSessionEvent) -> None:
        """会话结束时调用（fire-and-forget）。"""
        pass
