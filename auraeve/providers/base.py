"""LLM Provider 抽象基类。"""

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
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


def ensure_tool_call_id(
    raw_id: str | None,
    *,
    fallback_key: str,
    tool_name: str = "",
    arguments: dict[str, Any] | None = None,
) -> str:
    normalized = str(raw_id or "").strip()
    if normalized:
        return normalized
    payload = json.dumps(
        {
            "fallbackKey": fallback_key,
            "toolName": tool_name,
            "arguments": arguments or {},
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"call_{digest}"


def normalize_tool_call_requests(tool_calls: list[ToolCallRequest]) -> list[ToolCallRequest]:
    normalized: list[ToolCallRequest] = []
    for index, tool_call in enumerate(tool_calls):
        call_id = ensure_tool_call_id(
            tool_call.id,
            fallback_key=f"tool_call:{index}",
            tool_name=tool_call.name,
            arguments=tool_call.arguments,
        )
        if call_id == tool_call.id:
            normalized.append(tool_call)
            continue
        normalized.append(
            ToolCallRequest(
                id=call_id,
                name=tool_call.name,
                arguments=tool_call.arguments,
            )
        )
    return normalized


def normalize_tool_call_ids_in_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_messages: list[dict[str, Any]] = []
    pending_tool_call_ids: list[str] = []
    seen_tool_call_ids: set[str] = set()

    for message_index, message in enumerate(messages):
        normalized_message = dict(message)
        role = str(normalized_message.get("role") or "")

        if role == "assistant" and isinstance(normalized_message.get("tool_calls"), list):
            pending_tool_call_ids = []
            normalized_calls: list[dict[str, Any]] = []
            for call_index, raw_tool_call in enumerate(normalized_message["tool_calls"]):
                if not isinstance(raw_tool_call, dict):
                    normalized_calls.append(raw_tool_call)
                    continue
                tool_call = dict(raw_tool_call)
                function_payload = tool_call.get("function")
                function = dict(function_payload) if isinstance(function_payload, dict) else {}
                tool_name = str(function.get("name") or "")
                arguments = _coerce_tool_call_arguments(function.get("arguments"))
                call_id = ensure_tool_call_id(
                    tool_call.get("id"),
                    fallback_key=f"message:{message_index}:tool_call:{call_index}",
                    tool_name=tool_name,
                    arguments=arguments,
                )
                tool_call["id"] = call_id
                if function:
                    tool_call["function"] = function
                normalized_calls.append(tool_call)
                pending_tool_call_ids.append(call_id)
                seen_tool_call_ids.add(call_id)
            normalized_message["tool_calls"] = normalized_calls
        elif role == "tool":
            tool_call_id = str(normalized_message.get("tool_call_id") or "").strip()
            if not tool_call_id:
                if pending_tool_call_ids:
                    tool_call_id = pending_tool_call_ids.pop(0)
                    normalized_message["tool_call_id"] = tool_call_id
                else:
                    continue
            if tool_call_id not in seen_tool_call_ids:
                continue
            if tool_call_id in pending_tool_call_ids:
                pending_tool_call_ids.remove(tool_call_id)
        else:
            pending_tool_call_ids = []

        normalized_messages.append(normalized_message)

    return normalized_messages


def backfill_tool_context_start(messages: list[dict[str, Any]], start_index: int) -> int:
    start = max(0, min(start_index, len(messages)))
    while start > 0 and start < len(messages):
        current = messages[start]
        if str(current.get("role") or "") != "tool":
            break
        tool_call_id = str(current.get("tool_call_id") or "").strip()
        if not tool_call_id:
            break
        match_index = _find_matching_assistant_tool_call(messages, tool_call_id, start)
        if match_index is None:
            break
        start = match_index
    return start


def _find_matching_assistant_tool_call(
    messages: list[dict[str, Any]],
    tool_call_id: str,
    before_index: int,
) -> int | None:
    for index in range(before_index - 1, -1, -1):
        message = messages[index]
        if str(message.get("role") or "") != "assistant":
            continue
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for raw_tool_call in tool_calls:
            if not isinstance(raw_tool_call, dict):
                continue
            call_id = str(raw_tool_call.get("id") or "").strip()
            if call_id == tool_call_id:
                return index
    return None


def _coerce_tool_call_arguments(raw_arguments: Any) -> dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if isinstance(raw_arguments, str) and raw_arguments.strip():
        try:
            parsed = json.loads(raw_arguments)
        except Exception:  # noqa: BLE001
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


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
        text_delta_callback: Callable[[str], Awaitable[None]] | None = None,
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
