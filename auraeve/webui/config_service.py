from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

from loguru import logger

import auraeve.config as cfg
from auraeve.config.defaults import SENSITIVE_KEYS
from auraeve.config.runtime import split_hot_cold_keys
from auraeve.config.schema import build_webui_schema_groups
from auraeve.webui.schemas import (
    ConfigGetResponse,
    ConfigSchemaField,
    ConfigSchemaGroup,
    ConfigSchemaResponse,
    ConfigWriteResponse,
)

RuntimeApplyCallback = Callable[[dict[str, Any], list[str]], Awaitable[dict[str, Any] | None]]


def _serialize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    return value


def _mask_model_secrets(config: dict[str, Any]) -> dict[str, Any]:
    payload = dict(config)
    models = []
    for item in payload.get("LLM_MODELS") or []:
        if not isinstance(item, dict):
            continue
        model = dict(item)
        if isinstance(model.get("apiKey"), str) and model.get("apiKey"):
            model["apiKey"] = "********"
        models.append(model)
    payload["LLM_MODELS"] = models

    asr = payload.get("ASR")
    if isinstance(asr, dict):
        providers = []
        for item in asr.get("providers") or []:
            if not isinstance(item, dict):
                continue
            provider = dict(item)
            if isinstance(provider.get("apiKey"), str) and provider.get("apiKey"):
                provider["apiKey"] = "********"
            providers.append(provider)
        payload["ASR"] = {**asr, "providers": providers}
    return payload


class ConfigService:
    def __init__(
        self,
        config_path: Path | None = None,
        on_runtime_apply: RuntimeApplyCallback | None = None,
    ) -> None:
        self._config_path = config_path
        self._on_runtime_apply = on_runtime_apply

    def set_runtime_apply_callback(self, callback: RuntimeApplyCallback | None) -> None:
        self._on_runtime_apply = callback

    def get(self) -> ConfigGetResponse:
        snapshot = cfg.read_snapshot()
        payload = cfg.export_config(mask_sensitive=True)
        payload = _mask_model_secrets(payload)
        data = {
            "LLM_MODELS": _serialize(payload.get("LLM_MODELS") or []),
            "READ_ROUTING": _serialize(payload.get("READ_ROUTING") or {}),
            "ASR": _serialize(payload.get("ASR") or {}),
            **{
                k: _serialize(v)
                for k, v in payload.items()
                if k.isupper() and k not in {"LLM_MODELS", "READ_ROUTING", "ASR"}
            },
        }
        return ConfigGetResponse(
            config=data,
            baseHash=snapshot.base_hash,
            valid=snapshot.valid,
            issues=[*snapshot.issues, *snapshot.warnings],
        )

    def schema(self) -> ConfigSchemaResponse:
        groups: list[ConfigSchemaGroup] = []
        for grp in build_webui_schema_groups():
            fields: list[ConfigSchemaField] = []
            for field in grp["fields"]:
                fields.append(
                    ConfigSchemaField(
                        key=field["key"],
                        type=field["type"],
                        label=field["label"],
                        description=field["description"],
                        sensitive=field.get("sensitive", False),
                        restartRequired=field.get("restartRequired", False),
                    )
                )
            groups.append(ConfigSchemaGroup(key=grp["key"], title=grp["title"], fields=fields))
        return ConfigSchemaResponse(groups=groups)

    def set(self, base_hash: str, new_config: dict[str, Any]) -> ConfigWriteResponse:
        sanitized = self._sanitize_patch(new_config)
        ok, snapshot, changed, requires_restart, issues = cfg.write(sanitized, base_hash=base_hash)
        if not ok:
            return ConfigWriteResponse(
                ok=False,
                baseHash=snapshot.base_hash,
                changed=[],
                applied=[],
                requiresRestart=[],
                issues=issues,
            )
        return ConfigWriteResponse(
            ok=True,
            baseHash=snapshot.base_hash,
            changed=changed,
            applied=[],
            requiresRestart=sorted(set(requires_restart or changed)),
            issues=[],
        )

    async def apply(self, base_hash: str, new_config: dict[str, Any]) -> ConfigWriteResponse:
        sanitized = self._sanitize_patch(new_config)
        ok, snapshot, changed, requires_restart, issues = cfg.write(sanitized, base_hash=base_hash)
        if not ok:
            return ConfigWriteResponse(
                ok=False,
                baseHash=snapshot.base_hash,
                changed=[],
                applied=[],
                requiresRestart=[],
                issues=issues,
            )

        changed_hot, changed_cold = split_hot_cold_keys(changed)
        applied: list[str] = []
        requires_restart = sorted(set(requires_restart) | set(changed_cold))
        if self._on_runtime_apply is not None:
            runtime_patch = {key: snapshot.config.get(key) for key in changed_hot}
            if runtime_patch:
                try:
                    runtime_result = await self._on_runtime_apply(runtime_patch, changed_hot)
                    if runtime_result:
                        runtime_applied = self._normalize_key_list(runtime_result.get("applied"))
                        runtime_restart = self._normalize_key_list(runtime_result.get("requiresRestart"))
                        runtime_issues = self._normalize_issues(runtime_result.get("issues"))
                        applied = sorted(set(applied) | set(runtime_applied))
                        requires_restart = sorted(set(requires_restart) | set(runtime_restart))
                        issues = [*issues, *runtime_issues]
                        unresolved_hot = sorted(set(changed_hot) - set(applied) - set(requires_restart))
                        if unresolved_hot:
                            requires_restart = sorted(set(requires_restart) | set(unresolved_hot))
                            issues.append(
                                {
                                    "code": "runtime_apply_partial",
                                    "message": (
                                        "runtime hot-apply did not confirm some keys; restart required: "
                                        + ", ".join(unresolved_hot)
                                    ),
                                }
                            )
                except Exception as exc:
                    logger.warning(f"runtime apply callback failed: {exc}")
                    requires_restart = sorted(set(requires_restart) | set(changed_hot))
                    issues.append({"code": "runtime_apply_failed", "message": str(exc)})
        elif changed_hot:
            requires_restart = sorted(set(requires_restart) | set(changed_hot))
            issues.append(
                {
                    "code": "runtime_apply_unavailable",
                    "message": "runtime apply callback is not configured; restart required for hot keys.",
                }
            )

        return ConfigWriteResponse(
            ok=True,
            baseHash=snapshot.base_hash,
            changed=changed,
            applied=applied,
            requiresRestart=requires_restart,
            issues=issues,
        )

    def _sanitize_patch(self, patch: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        current_snapshot = cfg.read_snapshot()
        current_config = current_snapshot.config
        for key, value in patch.items():
            if key == "LLM_MODELS" and isinstance(value, list):
                existing_models = current_config.get("LLM_MODELS") if isinstance(current_config.get("LLM_MODELS"), list) else []
                existing_by_id = {
                    str(item.get("id") or ""): item
                    for item in existing_models
                    if isinstance(item, dict)
                }
                sanitized_models = []
                for idx, item in enumerate(value):
                    if not isinstance(item, dict):
                        continue
                    model = dict(item)
                    existing_model = existing_by_id.get(str(model.get("id") or ""))
                    if existing_model is None and idx < len(existing_models) and isinstance(existing_models[idx], dict):
                        existing_model = existing_models[idx]
                    api_key = model.get("apiKey")
                    if isinstance(api_key, str) and (not api_key.strip() or set(api_key.strip()) == {"*"}):
                        existing_api_key = existing_model.get("apiKey") if isinstance(existing_model, dict) else None
                        if isinstance(existing_api_key, str) and existing_api_key:
                            model["apiKey"] = existing_api_key
                        else:
                            model.pop("apiKey", None)
                    sanitized_models.append(model)
                out[key] = sanitized_models
                continue
            if key == "ASR" and isinstance(value, dict):
                asr = dict(value)
                current_asr = current_config.get("ASR") if isinstance(current_config.get("ASR"), dict) else {}
                existing_providers = current_asr.get("providers") if isinstance(current_asr.get("providers"), list) else []
                existing_by_id = {
                    str(item.get("id") or ""): item
                    for item in existing_providers
                    if isinstance(item, dict)
                }
                providers = []
                for idx, item in enumerate(asr.get("providers") or []):
                    if not isinstance(item, dict):
                        continue
                    provider = dict(item)
                    existing_provider = existing_by_id.get(str(provider.get("id") or ""))
                    if existing_provider is None and idx < len(existing_providers) and isinstance(existing_providers[idx], dict):
                        existing_provider = existing_providers[idx]
                    api_key = provider.get("apiKey")
                    if isinstance(api_key, str) and (not api_key.strip() or set(api_key.strip()) == {"*"}):
                        existing_api_key = existing_provider.get("apiKey") if isinstance(existing_provider, dict) else None
                        if isinstance(existing_api_key, str) and existing_api_key:
                            provider["apiKey"] = existing_api_key
                        else:
                            provider.pop("apiKey", None)
                    providers.append(provider)
                asr["providers"] = providers
                out[key] = asr
                continue
            if key in SENSITIVE_KEYS and isinstance(value, str):
                trimmed = value.strip()
                if trimmed == "" or set(trimmed) == {"*"}:
                    continue
            out[key] = value
        return out

    def _normalize_key_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            key = item.strip()
            if key and key not in out:
                out.append(key)
        return out

    def _normalize_issues(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        out: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                out.append(item)
        return out
