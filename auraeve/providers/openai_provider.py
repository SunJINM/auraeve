"""OpenAI 兼容 SDK Provider。"""

import json
import json_repair
import time
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

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        thinking_budget_tokens: int | None = None,
    ) -> LLMResponse:
        model = model or self.default_model
        max_tokens = max(1, max_tokens)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": normalize_tool_call_ids_in_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

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
            response = await self._client.chat.completions.create(**kwargs)
            return self._parse_response(response)
        except (_openai.RateLimitError, _openai.APIStatusError, _openai.APIConnectionError) as e:
            raise _classify_openai_error(e) from e
        except Exception as e:
            # 按文本特征二次分类（部分兼容接口不抛 openai 标准异常）
            raise _classify_openai_error(e) from e

    def _parse_response(self, response: Any) -> LLMResponse:
        """解析 OpenAI 格式的响应。"""
        choice = response.choices[0]
        message = choice.message

        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json_repair.loads(args)
                    except Exception:
                        args = {}
                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))
            tool_calls = normalize_tool_call_requests(tool_calls)

        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        # 部分模型（如 DeepSeek-R1）返回 reasoning_content
        reasoning_content = getattr(message, "reasoning_content", None)

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
            reasoning_content=reasoning_content,
        )

    def get_default_model(self) -> str:
        return self.default_model

    async def transcribe(self, audio_path: str, language: str = "zh") -> str | None:
        """使用 Whisper API 转录音频文件为文本。"""
        from loguru import logger
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
