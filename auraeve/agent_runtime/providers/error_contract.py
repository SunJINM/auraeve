"""Provider 错误契约：HTTP 状态码 → 结构化异常映射工具。"""

from auraeve.providers.base import (
    LLMCallError,
    RateLimitError,
    OverloadError,
    ContextOverflowError,
    AuthError,
    BillingError,
    ProviderAPIError,
    ProviderError,
)

__all__ = [
    "LLMCallError",
    "RateLimitError",
    "OverloadError",
    "ContextOverflowError",
    "AuthError",
    "BillingError",
    "ProviderAPIError",
    "ProviderError",
    "classify_http_error",
    "classify_exception",
]


def classify_http_error(status_code: int, message: str = "") -> LLMCallError:
    """将 HTTP 状态码映射到结构化异常。"""
    if status_code == 429:
        return RateLimitError(message)
    if status_code == 402:
        return BillingError(message)
    if status_code in (401, 403):
        return AuthError(message)
    if status_code in (502, 503, 529):
        return OverloadError(message)
    if status_code >= 500:
        return ProviderAPIError(message)
    return ProviderError(message)


def classify_exception(exc: Exception) -> LLMCallError:
    """
    将第三方库异常（litellm / openai）映射到结构化异常。

    按异常类名/消息进行模式匹配，不依赖 provider 具体类型。
    """
    cls_name = type(exc).__name__.lower()
    msg = str(exc).lower()

    # 已经是我们的结构化异常
    if isinstance(exc, LLMCallError):
        return exc

    # 限流
    if "ratelimit" in cls_name or "429" in msg or "rate limit" in msg:
        return RateLimitError(str(exc))

    # 过载
    if any(k in msg for k in ("overload", "capacity", "502", "503", "529")):
        return OverloadError(str(exc))

    # 上下文溢出
    if any(k in msg for k in (
        "context_length", "context length", "maximum context",
        "token limit", "too long", "input is too long",
    )):
        return ContextOverflowError(str(exc))

    # 认证
    if any(k in msg for k in ("401", "403", "unauthorized", "authentication", "invalid api key")):
        return AuthError(str(exc))

    # 计费
    if any(k in msg for k in ("402", "billing", "quota", "insufficient_quota", "payment")):
        return BillingError(str(exc))

    # 5xx 服务端
    if any(k in msg for k in ("500", "internal server error", "bad gateway")):
        return ProviderAPIError(str(exc))

    return ProviderError(str(exc))
