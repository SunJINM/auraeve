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
        data = {k: _serialize(v) for k, v in payload.items() if k.isupper()}
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
        for key, value in patch.items():
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
