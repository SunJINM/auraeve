from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

import auraeve.config as cfg
from auraeve.stt.audio_normalize import build_audio_meta
from auraeve.stt.cache import STTCache
from auraeve.stt.events import write_audit_line
from auraeve.stt.orchestrator import STTOrchestrator
from auraeve.stt.providers.factory import build_provider
from auraeve.stt.types import ProviderProfile, RuntimeConfig, STTRequest, STTResult


class STTRuntime:
    def __init__(self, runtime_config: RuntimeConfig) -> None:
        self._config = runtime_config
        self._cache = STTCache()
        self._orchestrator = self._build_orchestrator()

    def _build_orchestrator(self) -> STTOrchestrator:
        providers = []
        for profile in sorted(self._config.providers, key=lambda item: item.priority, reverse=True):
            if not profile.enabled:
                continue
            provider = build_provider(profile)
            if provider is None:
                logger.warning(f"Unknown STT provider id: {profile.id}")
                continue
            providers.append(provider)
        return STTOrchestrator(
            providers,
            timeout_ms=self._config.timeout_ms,
            retry_count=self._config.retry_count,
            failover_enabled=self._config.failover_enabled,
            max_concurrency=self._config.max_concurrency,
        )

    def reload(self, runtime_config: RuntimeConfig) -> None:
        self._config = runtime_config
        self._orchestrator = self._build_orchestrator()

    async def transcribe_file(
        self,
        file_path: str,
        *,
        channel: str,
        language: str | None = None,
        provider_profile: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        if not self._config.enabled:
            return None

        language_final = (language or self._config.default_language or "zh-CN").strip() or "zh-CN"
        request_id = str(uuid.uuid4())
        meta = dict(metadata or {})
        meta.setdefault("audio", build_audio_meta(file_path))

        cache_key = None
        if self._config.cache_enabled:
            try:
                content = Path(file_path).read_bytes()
                cache_key = self._cache.make_key(content, language_final, provider_profile)
                cached_text = self._cache.get(cache_key)
                if cached_text:
                    self._write_audit(
                        request_id=request_id,
                        channel=channel,
                        provider_selected="cache",
                        attempts=[],
                        latency_ms=0,
                        ok=True,
                        error="",
                        metadata=meta,
                    )
                    return cached_text
            except Exception:
                cache_key = None

        req = STTRequest(
            input_path=Path(file_path),
            channel=channel,
            language=language_final,
            provider_profile=provider_profile,
            metadata=meta,
        )
        result = await self._orchestrator.transcribe(req)

        self._write_audit(
            request_id=request_id,
            channel=channel,
            provider_selected=result.provider,
            attempts=result.attempts,
            latency_ms=result.latency_ms,
            ok=result.ok,
            error=result.error,
            metadata=meta,
        )

        if result.ok and result.text and self._config.cache_enabled and cache_key:
            self._cache.set(cache_key, result.text, self._config.cache_ttl_s)

        return result.text if result.ok else None

    def _write_audit(
        self,
        *,
        request_id: str,
        channel: str,
        provider_selected: str,
        attempts,
        latency_ms: int,
        ok: bool,
        error: str,
        metadata: dict[str, Any],
    ) -> None:
        payload = {
            "requestId": request_id,
            "channel": channel,
            "providerTried": [item.provider_id for item in attempts],
            "providerSelected": provider_selected,
            "latencyMs": latency_ms,
            "result": {
                "ok": ok,
                "error": error,
            },
            "audioMeta": metadata.get("audio", {}),
        }
        write_audit_line(payload)


def _normalize_provider_profile(raw: Any) -> ProviderProfile | None:
    if not isinstance(raw, dict):
        return None
    provider_id = str(raw.get("id") or "").strip()
    if not provider_id:
        return None

    return ProviderProfile(
        id=provider_id,
        enabled=bool(raw.get("enabled", True)),
        priority=int(raw.get("priority", 100)),
        model=str(raw.get("model") or "").strip(),
        api_base=str(raw.get("apiBase") or raw.get("api_base") or "").strip(),
        api_key=str(raw.get("apiKey") or raw.get("api_key") or "").strip(),
        formats=[str(x).strip().lower() for x in (raw.get("formats") or []) if str(x).strip()],
        timeout_ms=int(raw.get("timeoutMs", raw.get("timeout_ms", 15000)) or 15000),
        command=str(raw.get("command") or "").strip(),
        args_template=[str(x) for x in (raw.get("argsTemplate") or raw.get("args_template") or [])],
        options=dict(raw.get("options") or {}),
    )


def runtime_config_from_dict(config: dict[str, Any]) -> RuntimeConfig:
    providers_raw = config.get("STT_PROVIDERS") or []
    providers: list[ProviderProfile] = []
    if isinstance(providers_raw, list):
        for item in providers_raw:
            profile = _normalize_provider_profile(item)
            if profile is not None:
                providers.append(profile)

    return RuntimeConfig(
        enabled=bool(config.get("STT_ENABLED", True)),
        default_language=str(config.get("STT_DEFAULT_LANGUAGE") or "zh-CN"),
        timeout_ms=int(config.get("STT_TIMEOUT_MS", 15000)),
        max_concurrency=int(config.get("STT_MAX_CONCURRENCY", 4)),
        retry_count=int(config.get("STT_RETRY_COUNT", 1)),
        failover_enabled=bool(config.get("STT_FAILOVER_ENABLED", True)),
        cache_enabled=bool(config.get("STT_CACHE_ENABLED", True)),
        cache_ttl_s=int(config.get("STT_CACHE_TTL_S", 600)),
        providers=providers,
    )


def build_runtime_from_config(config: dict[str, Any] | None = None) -> STTRuntime:
    payload = dict(config or cfg.export_config(mask_sensitive=False))
    runtime_config = runtime_config_from_dict(payload)
    return STTRuntime(runtime_config=runtime_config)

