"""OpenAI 兼容 SDK Provider。"""

import json
import json_repair
from collections.abc import Awaitable, Callable
from typing import Any

from openai import AsyncOpenAI
import openai as _openai
from loguru import logger

from auraeve.providers.base import (
    LLMProvider, LLMResponse, ToolCallRequest,
    LLMCallError, RateLimitError, OverloadError,
    ContextOverflowError, AuthError, BillingError,
    normalize_tool_call_ids_in_messages, normalize_tool_call_requests,
)

# 上下文溢出的错误消息特征（各厂商不尽相同）
_CONTEXT_OVERFLOW_PATTERNS = [
    "context_length_exceeded",
    "context window",
    "maximum context length",
    "maximum token",
    "too many tokens",
    "token limit",
    "请求的token数超过",
    "context_overflow",
    "input is too long",
    "413 request entity too large",
    "request entity too large",
]

# 配额/计费错误特征
_BILLING_PATTERNS = [
    "insufficient_quota",
    "exceeded your current quota",
    "billing_hard_limit_reached",
    "quota exceeded",
    "out of credits",
]


def _classify_openai_error(e: Exception) -> LLMCallError:
    """将 OpenAI SDK 异常分类为 LLMCallError 子类。"""
    text = str(e).lower()

    if isinstance(e, _openai.RateLimitError):
        return RateLimitError(str(e))

    if isinstance(e, _openai.APIStatusError):
        code = e.status_code
        if code == 429:
            return RateLimitError(str(e))
        if code in (502, 503, 529):
            return OverloadError(str(e))
        if code in (401, 403):
            return AuthError(str(e))

    if any(p in text for p in _BILLING_PATTERNS):
        return BillingError(str(e))
    if any(p in text for p in _CONTEXT_OVERFLOW_PATTERNS):
        return ContextOverflowError(str(e))

    return LLMCallError(str(e))


class OpenAICompatibleProvider(LLMProvider):
    """
    基于 OpenAI Python SDK 的 LLM Provider。

    通过设置 api_base 支持任何 OpenAI 兼容接口，例如：
        - OpenAI 官方：  api_base=None, api_key="sk-..."
        - DeepSeek：     api_base="https://api.deepseek.com/v1"
        - OpenRouter：   api_base="https://openrouter.ai/api/v1"
        - 火山引擎：     api_base="https://ark.cn-beijing.volces.com/api/v3"
        - 本地 Ollama：  api_base="http://localhost:11434/v1"
    """

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        default_model: str = "gpt-4o",
        extra_headers: dict[str, str] | None = None,
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=api_base or None,
            default_headers=extra_headers or {},
        )

    # 推理模型关键词：这些模型使用 reasoning tokens，不支持 temperature/max_tokens
    _REASONING_MODEL_PATTERNS = ("o1", "o3", "o4", "codex", "reasoning")

    def _is_reasoning_model(self, model: str) -> bool:
        model_lower = model.lower()
        return any(p in model_lower for p in self._REASONING_MODEL_PATTERNS)

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
        model = model or self.default_model
        max_tokens = max(1, max_tokens)

        is_reasoning = self._is_reasoning_model(model)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": normalize_tool_call_ids_in_messages(messages),
            "stream": True,
        }

        if is_reasoning:
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens
            kwargs["temperature"] = temperature

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        # 推理模型 thinking 支持：
        # Claude 系列：传 thinking 块；其余模型通过 extra_body 传递（火山引擎 doubao-seed 等）
        if thinking_budget_tokens and thinking_budget_tokens > 0:
            if "claude" in model.lower():
                kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": thinking_budget_tokens,
                }
            else:
                kwargs.setdefault("extra_body", {})["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": thinking_budget_tokens,
                }

        try:
            logger.debug(
                f"[openai_provider] chat request model={model} "
                f"messages={len(kwargs['messages'])} "
                f"tools={len(kwargs.get('tools') or [])} "
                f"max_tokens={max_tokens} "
                f"is_reasoning={is_reasoning}"
            )
            stream = await self._client.chat.completions.create(**kwargs)
            return await self._consume_stream(stream, text_delta_callback=text_delta_callback)
        except (_openai.RateLimitError, _openai.APIStatusError, _openai.APIConnectionError) as e:
            raise _classify_openai_error(e) from e
        except Exception as e:
            # 按文本特征二次分类（部分兼容接口不抛 openai 标准异常）
            raise _classify_openai_error(e) from e

    async def _consume_stream(
        self,
        stream: Any,
        text_delta_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        """消费流式响应，拼接为完整的 LLMResponse。"""
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls_map: dict[int, dict[str, Any]] = {}
        finish_reason = "stop"
        usage = {}

        async for chunk in stream:
            if not chunk.choices:
                # 最后一个 chunk 可能只包含 usage
                if chunk.usage:
                    usage = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens,
                    }
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            if choice.finish_reason:
                finish_reason = choice.finish_reason

            if delta.content:
                content_parts.append(delta.content)
                if text_delta_callback:
                    await text_delta_callback(delta.content)

            rc = getattr(delta, "reasoning_content", None)
            if rc:
                reasoning_parts.append(rc)

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    entry = tool_calls_map[idx]
                    if tc_delta.id:
                        entry["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            entry["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            entry["arguments"] += tc_delta.function.arguments

            # usage 也可能在带 choices 的 chunk 里
            if chunk.usage:
                usage = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                    "total_tokens": chunk.usage.total_tokens,
                }

        content = "".join(content_parts) if content_parts else None
        reasoning_content = "".join(reasoning_parts) if reasoning_parts else None

        tool_calls: list[ToolCallRequest] = []
        for idx in sorted(tool_calls_map):
            entry = tool_calls_map[idx]
            args_str = entry["arguments"]
            if isinstance(args_str, str) and args_str.strip():
                try:
                    args = json_repair.loads(args_str)
                except Exception:
                    args = {}
            else:
                args = {}
            tool_calls.append(ToolCallRequest(
                id=entry["id"],
                name=entry["name"],
                arguments=args,
            ))
        if tool_calls:
            tool_calls = normalize_tool_call_requests(tool_calls)

        if not tool_calls and content is None:
            logger.warning(
                "[openai_provider] empty text response without tool calls; "
                f"finish_reason={finish_reason} "
                f"reasoning_content={bool(reasoning_content)}"
            )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            reasoning_content=reasoning_content,
        )

    def get_default_model(self) -> str:
        return self.default_model

    async def transcribe(self, audio_path: str, language: str = "zh") -> str | None:
        """使用 Whisper API 转录音频文件为文本。"""
        try:
            with open(audio_path, "rb") as f:
                result = await self._client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language=language,
                )
            text = result.text.strip()
            logger.info(f"音频转录完成：{text[:80]}")
            return text
        except Exception as e:
            logger.error(f"音频转录失败：{e}")
            return None


def build_openai_provider_from_model_card(card: dict[str, Any]) -> OpenAICompatibleProvider:
    api_base = card.get("apiBase")
    return OpenAICompatibleProvider(
        api_key=str(card.get("apiKey") or ""),
        api_base=api_base.strip() if isinstance(api_base, str) and api_base.strip() else None,
        default_model=str(card.get("model") or ""),
        extra_headers=dict(card.get("extraHeaders") or {}),
    )
