"""LLM Provider 抽象基类。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# =============================================================================
# LLM 调用错误分类体系（对齐 openclaw 的渐进式恢复哲学）
#
# 错误分三类：
#   可退避重试  → RateLimitError / OverloadError
#   可压缩重试  → ContextOverflowError
#   不可恢复    → AuthError / BillingError / LLMCallError（基类兜底）
# =============================================================================

class LLMCallError(Exception):
    """LLM 调用错误基类（不可恢复时的兜底）。"""


class RateLimitError(LLMCallError):
    """限流错误（HTTP 429）。可退避后重试。"""


class OverloadError(LLMCallError):
    """模型过载错误（HTTP 502/503/529）。可退避后重试。"""


class ContextOverflowError(LLMCallError):
    """上下文长度超限。可压缩历史消息后重试。"""


class AuthError(LLMCallError):
    """认证/授权错误（HTTP 401/403）。通常不可重试。"""


class BillingError(LLMCallError):
    """配额/计费错误。不可重试。"""


class ProviderAPIError(LLMCallError):
    """Provider API 层错误（5xx、网关不稳定）。可限次重试。"""


class ProviderError(LLMCallError):
    """未分类 Provider 错误兜底。"""


# =============================================================================

@dataclass
class ToolCallRequest:
    """LLM 返回的工具调用请求。"""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """LLM Provider 的响应结果。"""
    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    reasoning_content: str | None = None  # 部分模型（如 DeepSeek-R1）返回的思考内容

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMProvider(ABC):
    """LLM Provider 的抽象基类。"""

    def __init__(self, api_key: str | None = None, api_base: str | None = None):
        self.api_key = api_key
        self.api_base = api_base

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        thinking_budget_tokens: int | None = None,
    ) -> LLMResponse:
        """
        调用 LLM。

        成功返回 LLMResponse；失败抛出 LLMCallError 子类：
        - RateLimitError       → 外层退避后重试
        - OverloadError        → 外层退避后重试
        - ContextOverflowError → 外层压缩后重试
        - AuthError            → 不可重试
        - BillingError         → 不可重试
        - LLMCallError         → 通用失败，有限次重试
        """
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        pass

    async def transcribe(self, audio_path: str, language: str = "zh") -> str | None:
        """转录音频文件为文本（可选实现，默认不支持）。"""
        return None
