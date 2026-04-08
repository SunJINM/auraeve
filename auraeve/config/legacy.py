from __future__ import annotations

from copy import deepcopy
from typing import Any

from .defaults import DEFAULTS

_LEGACY_LLM_KEYS = {
    "LLM_MODEL",
    "LLM_API_KEY",
    "LLM_API_BASE",
    "LLM_EXTRA_HEADERS",
    "LLM_MAX_TOKENS",
    "LLM_TEMPERATURE",
    "LLM_THINKING_BUDGET_TOKENS",
}

_LEGACY_STT_KEYS = {
    "STT_ENABLED",
    "STT_DEFAULT_LANGUAGE",
    "STT_TIMEOUT_MS",
    "STT_MAX_CONCURRENCY",
    "STT_RETRY_COUNT",
    "STT_FAILOVER_ENABLED",
    "STT_CACHE_ENABLED",
    "STT_CACHE_TTL_S",
    "STT_PROVIDERS",
}


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
    return out


def _as_str_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in value.items():
        if isinstance(k, str) and isinstance(v, str):
            out[k] = v
    return out


def _as_non_empty_str(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _migrate_legacy_mcp_keys(raw_obj: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    out = dict(raw_obj)
    notes: list[str] = []
    has_legacy_servers = "MCP_SERVERS" in out
    has_legacy_reload = "MCP_HOT_RELOAD_ENABLED" in out

    if not has_legacy_servers and not has_legacy_reload:
        return out, notes

    legacy_servers = out.get("MCP_SERVERS")
    legacy_reload = out.get("MCP_HOT_RELOAD_ENABLED")

    if "MCP" not in out:
        servers: dict[str, Any] = {}
        if isinstance(legacy_servers, dict):
            for server_id, cfg in legacy_servers.items():
                sid = _as_non_empty_str(server_id)
                if not sid or not isinstance(cfg, dict):
                    continue
                transport = _as_non_empty_str(cfg.get("transport")).lower()
                if transport not in {"stdio", "http"}:
                    transport = "http" if _as_non_empty_str(cfg.get("url")) else "stdio"
                command = _as_non_empty_str(cfg.get("command")) or _as_non_empty_str(cfg.get("cmd"))
                url = _as_non_empty_str(cfg.get("url")) or _as_non_empty_str(cfg.get("endpoint"))
                server: dict[str, Any] = {
                    "enabled": bool(cfg.get("enabled", True)),
                    "transport": transport,
                    "command": command,
                    "args": _as_str_list(cfg.get("args")),
                    "env": _as_str_map(cfg.get("env")),
                    "url": url,
                    "headers": _as_str_map(cfg.get("headers")),
                    "toolPrefix": _as_non_empty_str(cfg.get("toolPrefix")),
                    "toolAllow": _as_str_list(cfg.get("toolAllow")),
                    "toolDeny": _as_str_list(cfg.get("toolDeny")),
                    "retry": {
                        "maxAttempts": int(cfg.get("retry", {}).get("maxAttempts", 3))
                        if isinstance(cfg.get("retry"), dict)
                        and isinstance(cfg.get("retry", {}).get("maxAttempts"), int)
                        else 3,
                        "backoffMs": int(cfg.get("retry", {}).get("backoffMs", 500))
                        if isinstance(cfg.get("retry"), dict)
                        and isinstance(cfg.get("retry", {}).get("backoffMs"), int)
                        else 500,
                    },
                    "healthcheck": {
                        "enabled": bool(cfg.get("healthcheck", {}).get("enabled", True))
                        if isinstance(cfg.get("healthcheck"), dict)
                        else True,
                        "intervalSec": int(cfg.get("healthcheck", {}).get("intervalSec", 60))
                        if isinstance(cfg.get("healthcheck"), dict)
                        and isinstance(cfg.get("healthcheck", {}).get("intervalSec"), int)
                        else 60,
                    },
                }
                servers[sid] = server

        reload_policy = "none" if legacy_reload is False else "diff"
        out["MCP"] = {
            "enabled": bool(servers),
            "reloadPolicy": reload_policy,
            "defaultTimeoutMs": 20000,
            "servers": servers,
        }
        notes.append("migrated legacy MCP_SERVERS/MCP_HOT_RELOAD_ENABLED to MCP")

    if has_legacy_servers:
        out.pop("MCP_SERVERS", None)
    if has_legacy_reload:
        out.pop("MCP_HOT_RELOAD_ENABLED", None)
        if "MCP" in out and isinstance(out.get("MCP"), dict):
            mcp_obj = dict(out["MCP"])
            if "reloadPolicy" not in mcp_obj:
                mcp_obj["reloadPolicy"] = "none" if legacy_reload is False else "diff"
                out["MCP"] = mcp_obj
    notes.append("removed legacy MCP keys: MCP_SERVERS/MCP_HOT_RELOAD_ENABLED")
    return out, notes


def _migrate_legacy_llm_keys(raw_obj: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    out = dict(raw_obj)
    notes: list[str] = []
    present = [key for key in _LEGACY_LLM_KEYS if key in out]
    if not present:
        return out, notes

    if "LLM_MODELS" not in out:
        default_model = deepcopy((DEFAULTS.get("LLM_MODELS") or [{}])[0])
        model_name = _as_non_empty_str(out.get("LLM_MODEL"))
        if model_name:
            default_model["model"] = model_name
        api_key = out.get("LLM_API_KEY")
        if isinstance(api_key, str):
            default_model["apiKey"] = api_key
        api_base = out.get("LLM_API_BASE")
        if api_base is None:
            default_model["apiBase"] = None
        elif isinstance(api_base, str):
            default_model["apiBase"] = api_base.strip() or None
        extra_headers = out.get("LLM_EXTRA_HEADERS")
        if isinstance(extra_headers, dict):
            default_model["extraHeaders"] = dict(extra_headers)
        max_tokens = out.get("LLM_MAX_TOKENS")
        if isinstance(max_tokens, int) and not isinstance(max_tokens, bool) and max_tokens >= 0:
            default_model["maxTokens"] = max_tokens
        temperature = out.get("LLM_TEMPERATURE")
        if _is_number(temperature):
            default_model["temperature"] = float(temperature)
        thinking_budget = out.get("LLM_THINKING_BUDGET_TOKENS")
        if isinstance(thinking_budget, int) and not isinstance(thinking_budget, bool) and thinking_budget >= 0:
            default_model["thinkingBudgetTokens"] = thinking_budget
        out["LLM_MODELS"] = [default_model]
        notes.append("migrated legacy LLM_* keys to LLM_MODELS")

    for key in _LEGACY_LLM_KEYS:
        out.pop(key, None)
    notes.append("removed legacy LLM keys")
    return out, notes


def _migrate_legacy_stt_keys(raw_obj: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    out = dict(raw_obj)
    notes: list[str] = []
    present = [key for key in _LEGACY_STT_KEYS if key in out]
    if not present:
        return out, notes

    if "ASR" not in out:
        asr = deepcopy(DEFAULTS.get("ASR") or {})
        if isinstance(out.get("STT_ENABLED"), bool):
            asr["enabled"] = out["STT_ENABLED"]
        language = out.get("STT_DEFAULT_LANGUAGE")
        if isinstance(language, str):
            asr["defaultLanguage"] = language
        for source, target in (
            ("STT_TIMEOUT_MS", "timeoutMs"),
            ("STT_MAX_CONCURRENCY", "maxConcurrency"),
            ("STT_RETRY_COUNT", "retryCount"),
            ("STT_CACHE_TTL_S", "cacheTtlSeconds"),
        ):
            value = out.get(source)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                asr[target] = value
        for source, target in (
            ("STT_FAILOVER_ENABLED", "failoverEnabled"),
            ("STT_CACHE_ENABLED", "cacheEnabled"),
        ):
            value = out.get(source)
            if isinstance(value, bool):
                asr[target] = value
        providers = out.get("STT_PROVIDERS")
        if isinstance(providers, list):
            normalized_providers: list[dict[str, Any]] = []
            for item in providers:
                if not isinstance(item, dict):
                    continue
                provider = dict(item)
                provider_type = _as_non_empty_str(provider.get("type")).lower()
                if provider_type not in {"openai", "whisper-cli", "funasr-local"}:
                    provider_id = _as_non_empty_str(provider.get("id")).lower()
                    if provider_id in {"openai", "whisper-cli", "funasr-local"}:
                        provider_type = provider_id
                    elif _as_non_empty_str(provider.get("command")):
                        provider_type = "whisper-cli"
                    elif _as_non_empty_str(provider.get("apiKey")) or _as_non_empty_str(provider.get("apiBase")):
                        provider_type = "openai"
                    else:
                        provider_type = "funasr-local"
                provider["type"] = provider_type
                normalized_providers.append(provider)
            asr["providers"] = normalized_providers
        out["ASR"] = asr
        notes.append("migrated legacy STT_* keys to ASR")

    for key in _LEGACY_STT_KEYS:
        out.pop(key, None)
    notes.append("removed legacy STT keys")
    return out, notes


def _migrate_legacy_media_understanding(raw_obj: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    out = dict(raw_obj)
    notes: list[str] = []
    if "MEDIA_UNDERSTANDING" not in out:
        return out, notes

    media = out.get("MEDIA_UNDERSTANDING")
    if "READ_ROUTING" not in out:
        routing = deepcopy(DEFAULTS.get("READ_ROUTING") or {})
        if isinstance(media, dict):
            if isinstance(media.get("imageFallbackEnabled"), bool):
                routing["imageFallbackEnabled"] = media["imageFallbackEnabled"]
            if isinstance(media.get("failWhenNoImageModel"), bool):
                routing["failWhenNoImageModel"] = media["failWhenNoImageModel"]
            prompt = media.get("imageToTextPrompt")
            if isinstance(prompt, str):
                routing["imageToTextPrompt"] = prompt
        out["READ_ROUTING"] = routing
        notes.append("migrated MEDIA_UNDERSTANDING to READ_ROUTING")

    out.pop("MEDIA_UNDERSTANDING", None)
    notes.append("removed legacy MEDIA_UNDERSTANDING key")
    return out, notes


def migrate_legacy_config_object(raw_obj: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    current = dict(raw_obj)
    notes: list[str] = []
    for migrate in (
        _migrate_legacy_llm_keys,
        _migrate_legacy_stt_keys,
        _migrate_legacy_media_understanding,
        _migrate_legacy_mcp_keys,
    ):
        current, extra = migrate(current)
        notes.extend(extra)
    return current, notes
