from __future__ import annotations

from pathlib import Path
from typing import Any

from .defaults import DEFAULTS, PATH_KEYS, SENSITIVE_KEYS
from auraeve.mcp import validate_mcp_config


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _validate_runtime_execution(
    value: Any,
    issues: list[dict[str, str]],
    path: str = "RUNTIME_EXECUTION",
) -> None:
    if not isinstance(value, dict):
        issues.append({"path": path, "message": f"expected object, got {_type_name(value)}"})
        return

    int_positive_fields = (
        "maxTurns",
        "maxToolCallsTotal",
        "maxToolCallsPerTurn",
        "maxWallTimeMs",
        "maxRecoveryAttempts",
        "toolConcurrency",
        "toolTimeoutMs",
    )
    for field in int_positive_fields:
        if field not in value:
            continue
        raw = value.get(field)
        if not isinstance(raw, int) or isinstance(raw, bool) or raw <= 0:
            issues.append(
                {
                    "path": f"{path}.{field}",
                    "message": f"expected positive integer, got {_type_name(raw)}",
                }
            )

    policy = value.get("toolFailurePolicy")
    if policy is not None and policy not in {"fail_fast", "best_effort", "threshold"}:
        issues.append(
            {
                "path": f"{path}.toolFailurePolicy",
                "message": 'expected one of ["fail_fast","best_effort","threshold"]',
            }
        )


def _validate_runtime_loop_guard(
    value: Any,
    issues: list[dict[str, str]],
    path: str = "RUNTIME_LOOP_GUARD",
) -> None:
    if not isinstance(value, dict):
        issues.append({"path": path, "message": f"expected object, got {_type_name(value)}"})
        return

    mode = value.get("mode")
    if mode is not None and mode not in {"strict", "balanced", "long_task"}:
        issues.append(
            {
                "path": f"{path}.mode",
                "message": 'expected one of ["strict","balanced","long_task"]',
            }
        )

    for field in ("fingerprintWindow", "repeatBlockThreshold", "slowdownBackoffMs"):
        if field not in value:
            continue
        raw = value.get(field)
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
            issues.append(
                {
                    "path": f"{path}.{field}",
                    "message": f"expected non-negative integer, got {_type_name(raw)}",
                }
            )

    on_repeat = value.get("onRepeat")
    if on_repeat is not None and on_repeat not in {"warn_inject", "block_tools", "slowdown"}:
        issues.append(
            {
                "path": f"{path}.onRepeat",
                "message": 'expected one of ["warn_inject","block_tools","slowdown"]',
            }
        )


def validate_config_object(raw: dict[str, Any]) -> tuple[bool, list[dict[str, str]]]:
    issues: list[dict[str, str]] = []
    allowed = set(DEFAULTS.keys()) | {"META"}

    for key in raw.keys():
        if key not in allowed:
            issues.append({"path": key, "message": "unknown config key"})

    for key, expected in DEFAULTS.items():
        if key not in raw:
            continue
        value = raw[key]
        if value is None and expected is None:
            continue
        if key in PATH_KEYS and isinstance(value, str):
            continue
        if isinstance(expected, bool):
            if not isinstance(value, bool):
                issues.append(
                    {
                        "path": key,
                        "message": f"expected boolean, got {_type_name(value)}",
                    }
                )
            continue
        if isinstance(expected, int) and not isinstance(expected, bool):
            if not isinstance(value, int) or isinstance(value, bool):
                issues.append(
                    {
                        "path": key,
                        "message": f"expected integer, got {_type_name(value)}",
                    }
                )
            continue
        if isinstance(expected, float):
            if not _is_number(value):
                issues.append(
                    {
                        "path": key,
                        "message": f"expected number, got {_type_name(value)}",
                    }
                )
            continue
        if isinstance(expected, str):
            if not isinstance(value, str):
                issues.append(
                    {
                        "path": key,
                        "message": f"expected string, got {_type_name(value)}",
                    }
                )
            continue
        if isinstance(expected, list):
            if not isinstance(value, list):
                issues.append(
                    {
                        "path": key,
                        "message": f"expected array, got {_type_name(value)}",
                    }
                )
            continue
        if isinstance(expected, dict):
            if not isinstance(value, dict):
                issues.append(
                    {
                        "path": key,
                        "message": f"expected object, got {_type_name(value)}",
                    }
                )
            continue
        if expected is None and value is not None and not isinstance(value, str):
            issues.append(
                {
                    "path": key,
                    "message": f"expected string|null, got {_type_name(value)}",
                }
            )

    if "META" in raw and not isinstance(raw.get("META"), dict):
        issues.append({"path": "META", "message": f"expected object, got {_type_name(raw.get('META'))}"})

    agents_defaults = raw.get("AGENTS_DEFAULTS")
    if isinstance(agents_defaults, dict):
        if "workspace" in agents_defaults:
            workspace = agents_defaults.get("workspace")
            if workspace is not None and not isinstance(workspace, str):
                issues.append(
                    {
                        "path": "AGENTS_DEFAULTS.workspace",
                        "message": f"expected string, got {_type_name(workspace)}",
                    }
                )

    agents_list = raw.get("AGENTS_LIST")
    if isinstance(agents_list, list):
        for idx, item in enumerate(agents_list):
            if not isinstance(item, dict):
                issues.append(
                    {
                        "path": f"AGENTS_LIST[{idx}]",
                        "message": f"expected object, got {_type_name(item)}",
                    }
                )
                continue
            agent_id = item.get("id")
            if not isinstance(agent_id, str) or not agent_id.strip():
                issues.append(
                    {
                        "path": f"AGENTS_LIST[{idx}].id",
                        "message": "expected non-empty string",
                    }
                )
            if "workspace" in item:
                workspace = item.get("workspace")
                if workspace is not None and not isinstance(workspace, str):
                    issues.append(
                        {
                            "path": f"AGENTS_LIST[{idx}].workspace",
                            "message": f"expected string, got {_type_name(workspace)}",
                        }
                    )

    stt_providers = raw.get("STT_PROVIDERS")
    if isinstance(stt_providers, list):
        for idx, item in enumerate(stt_providers):
            if not isinstance(item, dict):
                issues.append(
                    {
                        "path": f"STT_PROVIDERS[{idx}]",
                        "message": f"expected object, got {_type_name(item)}",
                    }
                )
                continue
            provider_id = item.get("id")
            if not isinstance(provider_id, str) or not provider_id.strip():
                issues.append(
                    {
                        "path": f"STT_PROVIDERS[{idx}].id",
                        "message": "expected non-empty string",
                    }
                )

    if "RUNTIME_EXECUTION" in raw:
        _validate_runtime_execution(raw.get("RUNTIME_EXECUTION"), issues)
    if "RUNTIME_LOOP_GUARD" in raw:
        _validate_runtime_loop_guard(raw.get("RUNTIME_LOOP_GUARD"), issues)
    if "MCP" in raw:
        issues.extend(validate_mcp_config(raw.get("MCP")))

    return (len(issues) == 0, issues)


def normalize_config_object(raw: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULTS)
    merged.update(raw)

    agents_defaults = merged.get("AGENTS_DEFAULTS")
    if not isinstance(agents_defaults, dict):
        merged["AGENTS_DEFAULTS"] = {}
    else:
        ws = agents_defaults.get("workspace")
        merged["AGENTS_DEFAULTS"] = {"workspace": ws.strip()} if isinstance(ws, str) and ws.strip() else {}

    agents_list = merged.get("AGENTS_LIST")
    if not isinstance(agents_list, list):
        merged["AGENTS_LIST"] = []
    else:
        normalized_agents: list[dict[str, str]] = []
        for item in agents_list:
            if not isinstance(item, dict):
                continue
            agent_id = item.get("id")
            if not isinstance(agent_id, str) or not agent_id.strip():
                continue
            out: dict[str, str] = {"id": agent_id.strip()}
            workspace = item.get("workspace")
            if isinstance(workspace, str) and workspace.strip():
                out["workspace"] = workspace.strip()
            normalized_agents.append(out)
        merged["AGENTS_LIST"] = normalized_agents

    for key in PATH_KEYS:
        value = merged.get(key)
        if isinstance(value, Path):
            merged[key] = str(value)

    runtime_execution_defaults = DEFAULTS.get("RUNTIME_EXECUTION", {})
    runtime_execution = merged.get("RUNTIME_EXECUTION")
    if not isinstance(runtime_execution, dict):
        merged["RUNTIME_EXECUTION"] = dict(runtime_execution_defaults)
    else:
        normalized_runtime_execution = dict(runtime_execution_defaults)
        normalized_runtime_execution.update(runtime_execution)
        merged["RUNTIME_EXECUTION"] = normalized_runtime_execution

    runtime_loop_defaults = DEFAULTS.get("RUNTIME_LOOP_GUARD", {})
    runtime_loop_guard = merged.get("RUNTIME_LOOP_GUARD")
    if not isinstance(runtime_loop_guard, dict):
        merged["RUNTIME_LOOP_GUARD"] = dict(runtime_loop_defaults)
    else:
        normalized_runtime_loop = dict(runtime_loop_defaults)
        normalized_runtime_loop.update(runtime_loop_guard)
        merged["RUNTIME_LOOP_GUARD"] = normalized_runtime_loop
    return merged


_SCHEMA_GROUPS: list[tuple[str, str, list[str]]] = [
    (
        "llm",
        "模型配置",
        [
            "LLM_MODEL",
            "LLM_API_BASE",
            "LLM_API_KEY",
            "LLM_EXTRA_HEADERS",
            "LLM_MAX_TOKENS",
            "LLM_TEMPERATURE",
            "LLM_MAX_TOOL_ITERATIONS",
            "RUNTIME_EXECUTION",
            "RUNTIME_LOOP_GUARD",
            "LLM_MEMORY_WINDOW",
            "LLM_THINKING_BUDGET_TOKENS",
        ],
    ),
    (
        "runtime",
        "运行时配置",
        [
            "TOKEN_BUDGET",
            "COMPACTION_THRESHOLD_RATIO",
            "RUNTIME_HOT_APPLY_ENABLED",
            "USE_UNIFIED_TOOL_ASSEMBLER",
            "GLOBAL_DENY_TOOLS",
            "SESSION_TOOL_POLICY",
            "MAX_GLOBAL_SUBAGENT_CONCURRENT",
            "MAX_SESSION_SUBAGENT_CONCURRENT",
        ],
    ),
    (
        "channels",
        "渠道配置",
        [
            "DINGTALK_ENABLED",
            "DINGTALK_CLIENT_ID",
            "DINGTALK_CLIENT_SECRET",
            "DINGTALK_ALLOW_FROM",
            "NAPCAT_ENABLED",
            "NAPCAT_WS_URL",
            "NAPCAT_ACCESS_TOKEN",
            "NAPCAT_OWNER_QQ",
            "NAPCAT_ALLOW_FROM",
            "NAPCAT_ALLOW_GROUPS",
            "CHANNEL_USERS",
            "NOTIFY_CHANNEL",
        ],
    ),
    (
        "stt",
        "语音转写配置",
        [
            "STT_ENABLED",
            "STT_DEFAULT_LANGUAGE",
            "STT_TIMEOUT_MS",
            "STT_MAX_CONCURRENCY",
            "STT_RETRY_COUNT",
            "STT_FAILOVER_ENABLED",
            "STT_CACHE_ENABLED",
            "STT_CACHE_TTL_S",
            "STT_PROVIDERS",
        ],
    ),
    (
        "plugins",
        "插件配置",
        [
            "PLUGINS_AUTO_DISCOVERY_ENABLED",
            "PLUGINS_ENABLED",
            "PLUGINS_LOAD_PATHS",
            "PLUGINS_ALLOW",
            "PLUGINS_DENY",
            "PLUGINS_ENTRIES",
        ],
    ),
    (
        "skills",
        "技能配置",
        [
            "SKILLS_ENABLED",
            "SKILLS_ENTRIES",
            "SKILLS_LOAD_EXTRA_DIRS",
            "SKILLS_INSTALL_NODE_MANAGER",
            "SKILLS_INSTALL_PREFER_BREW",
            "SKILLS_INSTALL_TIMEOUT_MS",
            "SKILLS_SECURITY_ALLOWED_DOWNLOAD_DOMAINS",
            "SKILLS_LIMIT_MAX_IN_PROMPT",
            "SKILLS_LIMIT_MAX_PROMPT_CHARS",
            "SKILLS_LIMIT_MAX_FILE_BYTES",
        ],
    ),
        (
        "logging",
        "日志与可观测",
        [
            "LOGGING",
        ],
    ),(
        "webui",
        "WebUI 配置",
        [
            "WEBUI_ENABLED",
            "WEBUI_HOST",
            "WEBUI_PORT",
            "WEBUI_TOKEN",
            "WEBUI_OWNER_USER_ID",
        ],
    ),
    (
        "mcp",
        "MCP 配置",
        [
            "MCP",
        ],
    ),
    (
        "storage",
        "存储与路径",
        [
            "AGENTS_DEFAULTS",
            "AGENTS_LIST",
            "WORKSPACE_PATH",
            "SESSIONS_DIR",
            "VECTOR_DB_PATH",
            "CONTEXT_ENGINE",
            "EMBEDDING_MODEL",
            "EMBEDDING_API_KEY",
            "EMBEDDING_API_BASE",
            "MEMORY_SEARCH_LIMIT",
            "MEMORY_VECTOR_WEIGHT",
            "MEMORY_TEXT_WEIGHT",
            "MEMORY_MMR_LAMBDA",
            "MEMORY_TEMPORAL_HALF_LIFE_DAYS",
            "MEMORY_INCLUDE_SESSIONS",
            "MEMORY_SESSIONS_MAX_MESSAGES",
        ],
    ),
    (
        "node",
        "节点系统",
        [
            "NODE_ENABLED",
            "NODE_HOST",
            "NODE_PORT",
            "NODE_TOKENS",
        ],
    ),
    (
        "heartbeat",
        "心跳配置",
        [
            "HEARTBEAT_ENABLED",
            "HEARTBEAT_INTERVAL_S",
        ],
    ),
    (
        "tools",
        "工具与安全",
        [
            "BRAVE_API_KEY",
            "EXEC_TIMEOUT",
            "RESTRICT_TO_WORKSPACE",
            "GIT_USERNAME",
            "GIT_TOKEN",
            "MEDIA_UNDERSTANDING",
            "OWNER_QQ",
        ],
    ),
]

HOT_KEYS = {
    "LLM_TEMPERATURE",
    "LLM_MAX_TOKENS",
    "LLM_MAX_TOOL_ITERATIONS",
    "RUNTIME_EXECUTION",
    "RUNTIME_LOOP_GUARD",
    "LLM_MEMORY_WINDOW",
    "TOKEN_BUDGET",
    "HEARTBEAT_INTERVAL_S",
    "HEARTBEAT_ENABLED",
    "MCP",
    "SESSION_TOOL_POLICY",
    "GLOBAL_DENY_TOOLS",
    "DINGTALK_ENABLED",
    "DINGTALK_CLIENT_ID",
    "DINGTALK_CLIENT_SECRET",
    "DINGTALK_ALLOW_FROM",
    "NAPCAT_ENABLED",
    "NAPCAT_WS_URL",
    "NAPCAT_ACCESS_TOKEN",
    "NAPCAT_ALLOW_FROM",
    "NAPCAT_ALLOW_GROUPS",
    "NAPCAT_OWNER_QQ",
    "STT_ENABLED",
    "STT_DEFAULT_LANGUAGE",
    "STT_TIMEOUT_MS",
    "STT_MAX_CONCURRENCY",
    "STT_RETRY_COUNT",
    "STT_FAILOVER_ENABLED",
    "STT_CACHE_ENABLED",
    "STT_CACHE_TTL_S",
    "STT_PROVIDERS",
    "MEDIA_UNDERSTANDING",
    "CHANNEL_USERS",
    "NOTIFY_CHANNEL",
    "PLUGINS_AUTO_DISCOVERY_ENABLED",
    "PLUGINS_ENABLED",
    "PLUGINS_LOAD_PATHS",
    "PLUGINS_ALLOW",
    "PLUGINS_DENY",
    "PLUGINS_ENTRIES",
    "SKILLS_ENABLED",
    "SKILLS_ENTRIES",
    "SKILLS_LOAD_EXTRA_DIRS",
    "SKILLS_INSTALL_NODE_MANAGER",
    "SKILLS_INSTALL_PREFER_BREW",
    "SKILLS_INSTALL_TIMEOUT_MS",
    "SKILLS_SECURITY_ALLOWED_DOWNLOAD_DOMAINS",
    "SKILLS_LIMIT_MAX_IN_PROMPT",
    "SKILLS_LIMIT_MAX_PROMPT_CHARS",
    "SKILLS_LIMIT_MAX_FILE_BYTES",
}

COLD_KEYS = {key for key in DEFAULTS.keys() if key not in HOT_KEYS}

_LABEL_OVERRIDES = {
    "AGENTS_DEFAULTS": "多 Agent 默认配置",
    "AGENTS_LIST": "多 Agent 列表",
    "LLM_MODEL": "模型名称",
    "LLM_API_BASE": "API Base URL",
    "LLM_API_KEY": "API Key",
    "RUNTIME_EXECUTION": "执行预算与并发",
    "RUNTIME_LOOP_GUARD": "循环防护策略",
    "WEBUI_TOKEN": "访问令牌",
    "WORKSPACE_PATH": "工作区路径",
    "SESSIONS_DIR": "会话目录",
    "VECTOR_DB_PATH": "向量库路径",
}

_DESCRIPTION_OVERRIDES = {
    "AGENTS_DEFAULTS": "默认 agent 配置（如 workspace）。",
    "AGENTS_LIST": "agent 列表，每项可定义 id/workspace。",
    "STT_PROVIDERS": "语音转写 provider 列表（按 priority 从高到低尝试）。",
    "LLM_MODEL": "OpenAI 兼容模型名。",
    "LLM_API_BASE": "为空时使用官方默认地址。",
    "LLM_API_KEY": "模型 API Key。",
    "RUNTIME_EXECUTION": "运行时执行预算与工具并发策略。",
    "RUNTIME_LOOP_GUARD": "循环检测与降速/阻断策略。",
    "MCP": "MCP runtime 配置（servers/reloadPolicy/timeout）。",
    "PLUGINS_ENTRIES": "按插件 ID 的启停与配置。",
    "SKILLS_ENTRIES": "按技能 key 的启停与配置。",
}


def _infer_field_type(default_value: Any) -> str:
    if isinstance(default_value, bool):
        return "boolean"
    if isinstance(default_value, int) and not isinstance(default_value, bool):
        return "integer"
    if isinstance(default_value, float):
        return "number"
    if isinstance(default_value, dict):
        return "object"
    if isinstance(default_value, list):
        return "array"
    return "string"


def _default_label(key: str) -> str:
    if key in _LABEL_OVERRIDES:
        return _LABEL_OVERRIDES[key]
    return key


def _default_description(key: str) -> str:
    if key in _DESCRIPTION_OVERRIDES:
        return _DESCRIPTION_OVERRIDES[key]
    return f"配置项 {key}"


def build_webui_schema_groups() -> list[dict[str, Any]]:
    used: set[str] = set()
    groups: list[dict[str, Any]] = []
    for group_key, title, keys in _SCHEMA_GROUPS:
        fields: list[dict[str, Any]] = []
        for key in keys:
            if key not in DEFAULTS:
                continue
            used.add(key)
            fields.append(
                {
                    "key": key,
                    "type": _infer_field_type(DEFAULTS[key]),
                    "label": _default_label(key),
                    "description": _default_description(key),
                    "sensitive": key in SENSITIVE_KEYS,
                    "restartRequired": key not in HOT_KEYS,
                }
            )
        if fields:
            groups.append({"key": group_key, "title": title, "fields": fields})

    extra_fields: list[dict[str, Any]] = []
    for key in sorted(DEFAULTS.keys()):
        if key in used:
            continue
        extra_fields.append(
            {
                "key": key,
                "type": _infer_field_type(DEFAULTS[key]),
                "label": _default_label(key),
                "description": _default_description(key),
                "sensitive": key in SENSITIVE_KEYS,
                "restartRequired": key not in HOT_KEYS,
            }
        )
    if extra_fields:
        groups.append({"key": "advanced", "title": "高级", "fields": extra_fields})
    return groups

