"""插件系统：Plugin Hook 基础设施。"""

from .base import (
    Plugin,
    HookBeforePromptBuildEvent,
    HookBeforePromptBuildResult,
    HookBeforeToolCallEvent,
    HookBeforeToolCallResult,
    HookAfterToolCallEvent,
    HookMessageSendingEvent,
    HookMessageSendingResult,
    HookBeforeModelResolveEvent,
    HookBeforeModelResolveResult,
    HookSessionEvent,
)
from .hooks import HookRunner
from .registry import PluginRegistry

__all__ = [
    "Plugin",
    "HookBeforePromptBuildEvent",
    "HookBeforePromptBuildResult",
    "HookBeforeToolCallEvent",
    "HookBeforeToolCallResult",
    "HookAfterToolCallEvent",
    "HookMessageSendingEvent",
    "HookMessageSendingResult",
    "HookBeforeModelResolveEvent",
    "HookBeforeModelResolveResult",
    "HookSessionEvent",
    "HookRunner",
    "PluginRegistry",
]
