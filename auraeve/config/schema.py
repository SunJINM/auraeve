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
        "子体系统",
        [
            "NODE_ENABLED",
            "NODE_HOST",
            "NODE_TOKENS",
            "SUBAGENT_WS_PORT",
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
    # 模型配置
    "LLM_MODEL": "模型名称",
    "LLM_API_BASE": "API 地址",
    "LLM_API_KEY": "API 密钥",
    "LLM_EXTRA_HEADERS": "额外请求头",
    "LLM_MAX_TOKENS": "最大 Token 数",
    "LLM_TEMPERATURE": "温度",
    "LLM_MAX_TOOL_ITERATIONS": "工具最大迭代次数",
    "LLM_MEMORY_WINDOW": "记忆窗口",
    "LLM_THINKING_BUDGET_TOKENS": "思考预算 Token",
    "RUNTIME_EXECUTION": "执行预算与并发",
    "RUNTIME_LOOP_GUARD": "循环防护策略",
    # 运行时配置
    "TOKEN_BUDGET": "Token 预算",
    "COMPACTION_THRESHOLD_RATIO": "上下文压缩阈值",
    "RUNTIME_HOT_APPLY_ENABLED": "热更新",
    "USE_UNIFIED_TOOL_ASSEMBLER": "统一工具装配器",
    "GLOBAL_DENY_TOOLS": "全局禁用工具",
    "SESSION_TOOL_POLICY": "会话工具策略",
    "MAX_GLOBAL_SUBAGENT_CONCURRENT": "全局子体并发上限",
    "MAX_SESSION_SUBAGENT_CONCURRENT": "会话子体并发上限",
    # 渠道配置
    "DINGTALK_ENABLED": "启用钉钉",
    "DINGTALK_CLIENT_ID": "钉钉 Client ID",
    "DINGTALK_CLIENT_SECRET": "钉钉 Client Secret",
    "DINGTALK_ALLOW_FROM": "钉钉允许来源",
    "NAPCAT_ENABLED": "启用 NapCat",
    "NAPCAT_WS_URL": "NapCat WebSocket 地址",
    "NAPCAT_ACCESS_TOKEN": "NapCat 访问令牌",
    "NAPCAT_OWNER_QQ": "NapCat 主人 QQ",
    "NAPCAT_ALLOW_FROM": "NapCat 允许来源",
    "NAPCAT_ALLOW_GROUPS": "NapCat 允许群组",
    "CHANNEL_USERS": "渠道用户映射",
    "NOTIFY_CHANNEL": "通知渠道",
    # 语音转写
    "STT_ENABLED": "启用语音转写",
    "STT_DEFAULT_LANGUAGE": "默认语言",
    "STT_TIMEOUT_MS": "转写超时(ms)",
    "STT_MAX_CONCURRENCY": "最大并发数",
    "STT_RETRY_COUNT": "重试次数",
    "STT_FAILOVER_ENABLED": "故障转移",
    "STT_CACHE_ENABLED": "启用缓存",
    "STT_CACHE_TTL_S": "缓存过期(秒)",
    "STT_PROVIDERS": "转写引擎列表",
    # 插件
    "PLUGINS_AUTO_DISCOVERY_ENABLED": "自动发现插件",
    "PLUGINS_ENABLED": "启用插件系统",
    "PLUGINS_LOAD_PATHS": "插件加载路径",
    "PLUGINS_ALLOW": "插件白名单",
    "PLUGINS_DENY": "插件黑名单",
    "PLUGINS_ENTRIES": "插件条目配置",
    # 技能
    "SKILLS_ENABLED": "启用技能系统",
    "SKILLS_ENTRIES": "技能条目配置",
    "SKILLS_LOAD_EXTRA_DIRS": "额外技能目录",
    "SKILLS_INSTALL_NODE_MANAGER": "Node 包管理器",
    "SKILLS_INSTALL_PREFER_BREW": "优先使用 Brew",
    "SKILLS_INSTALL_TIMEOUT_MS": "安装超时(ms)",
    "SKILLS_SECURITY_ALLOWED_DOWNLOAD_DOMAINS": "允许下载域名",
    "SKILLS_LIMIT_MAX_IN_PROMPT": "Prompt 最大技能数",
    "SKILLS_LIMIT_MAX_PROMPT_CHARS": "Prompt 最大字符数",
    "SKILLS_LIMIT_MAX_FILE_BYTES": "技能文件大小上限",
    # 日志
    "LOGGING": "日志配置",
    # WebUI
    "WEBUI_ENABLED": "启用 WebUI",
    "WEBUI_HOST": "监听地址",
    "WEBUI_PORT": "监听端口",
    "WEBUI_TOKEN": "访问令牌",
    "WEBUI_OWNER_USER_ID": "管理员用户 ID",
    # MCP
    "MCP": "MCP 配置",
    # 存储与路径
    "AGENTS_DEFAULTS": "多 Agent 默认配置",
    "AGENTS_LIST": "多 Agent 列表",
    "WORKSPACE_PATH": "工作区路径",
    "SESSIONS_DIR": "会话目录",
    "VECTOR_DB_PATH": "向量库路径",
    "CONTEXT_ENGINE": "上下文引擎",
    "EMBEDDING_MODEL": "嵌入模型",
    "EMBEDDING_API_KEY": "嵌入 API 密钥",
    "EMBEDDING_API_BASE": "嵌入 API 地址",
    "MEMORY_SEARCH_LIMIT": "记忆检索条数",
    "MEMORY_VECTOR_WEIGHT": "向量权重",
    "MEMORY_TEXT_WEIGHT": "文本权重",
    "MEMORY_MMR_LAMBDA": "MMR 多样性系数",
    "MEMORY_TEMPORAL_HALF_LIFE_DAYS": "时间衰减半衰期(天)",
    "MEMORY_INCLUDE_SESSIONS": "包含会话记忆",
    "MEMORY_SESSIONS_MAX_MESSAGES": "会话记忆最大条数",
    # 子体系统
    "NODE_ENABLED": "启用子体系统",
    "NODE_HOST": "子体监听地址",
    "NODE_TOKENS": "子体认证令牌",
    "SUBAGENT_WS_PORT": "子体 WebSocket 端口",
    # 心跳
    "HEARTBEAT_ENABLED": "启用心跳",
    "HEARTBEAT_INTERVAL_S": "心跳间隔(秒)",
    # 工具与安全
    "BRAVE_API_KEY": "Brave 搜索 API Key",
    "EXEC_TIMEOUT": "命令执行超时(秒)",
    "RESTRICT_TO_WORKSPACE": "限制在工作区内",
    "GIT_USERNAME": "Git 用户名",
    "GIT_TOKEN": "Git 令牌",
    "MEDIA_UNDERSTANDING": "多媒体理解",
    "OWNER_QQ": "主人 QQ 号",
}

_DESCRIPTION_OVERRIDES = {
    # 模型配置
    "LLM_MODEL": "OpenAI 兼容模型名称，如 gpt-4o-mini、deepseek-chat 等。",
    "LLM_API_BASE": "模型 API 地址，留空则使用官方默认地址。",
    "LLM_API_KEY": "模型服务的 API 密钥。",
    "LLM_EXTRA_HEADERS": "调用模型时附加的 HTTP 请求头（JSON 对象）。",
    "LLM_MAX_TOKENS": "单次模型调用返回的最大 Token 数量。",
    "LLM_TEMPERATURE": "生成随机性，值越高回复越多样，范围 0-2。",
    "LLM_MAX_TOOL_ITERATIONS": "单轮对话中模型调用工具的最大迭代次数。",
    "LLM_MEMORY_WINDOW": "发送给模型的历史消息条数上限。",
    "LLM_THINKING_BUDGET_TOKENS": "模型思考链预算 Token 数，0 表示关闭。",
    "RUNTIME_EXECUTION": "运行时执行预算与工具并发策略（JSON 对象）。",
    "RUNTIME_LOOP_GUARD": "循环检测与降速/阻断策略（JSON 对象）。",
    # 运行时配置
    "TOKEN_BUDGET": "单次会话的总 Token 预算，超出后触发上下文压缩。",
    "COMPACTION_THRESHOLD_RATIO": "Token 用量达到预算的此比例时触发压缩，范围 0-1。",
    "RUNTIME_HOT_APPLY_ENABLED": "允许配置修改后无需重启即刻生效。",
    "USE_UNIFIED_TOOL_ASSEMBLER": "使用统一工具装配器合并所有工具来源。",
    "GLOBAL_DENY_TOOLS": "全局禁用的工具名称列表（JSON 数组）。",
    "SESSION_TOOL_POLICY": "按会话/场景的工具权限策略（JSON 对象）。",
    "MAX_GLOBAL_SUBAGENT_CONCURRENT": "全局同时运行的子体数量上限。",
    "MAX_SESSION_SUBAGENT_CONCURRENT": "单个会话同时运行的子体数量上限。",
    # 渠道配置
    "DINGTALK_ENABLED": "是否启用钉钉机器人渠道。",
    "DINGTALK_CLIENT_ID": "钉钉应用的 Client ID。",
    "DINGTALK_CLIENT_SECRET": "钉钉应用的 Client Secret。",
    "DINGTALK_ALLOW_FROM": "允许接收消息的钉钉用户/群组 ID 列表。",
    "NAPCAT_ENABLED": "是否启用 NapCat (QQ) 渠道。",
    "NAPCAT_WS_URL": "NapCat 的 WebSocket 连接地址。",
    "NAPCAT_ACCESS_TOKEN": "NapCat 的访问令牌。",
    "NAPCAT_OWNER_QQ": "机器人主人的 QQ 号码，拥有最高权限。",
    "NAPCAT_ALLOW_FROM": "允许接收私聊消息的 QQ 号码列表。",
    "NAPCAT_ALLOW_GROUPS": "允许接收群消息的 QQ 群号列表。",
    "CHANNEL_USERS": "渠道 ID 到内部用户 ID 的映射关系（JSON 对象）。",
    "NOTIFY_CHANNEL": "系统通知发送的目标渠道标识。",
    # 语音转写
    "STT_ENABLED": "是否启用语音转文字功能。",
    "STT_DEFAULT_LANGUAGE": "语音识别的默认语言代码，如 zh-CN。",
    "STT_TIMEOUT_MS": "单次语音转写的超时时间（毫秒）。",
    "STT_MAX_CONCURRENCY": "语音转写的最大并发请求数。",
    "STT_RETRY_COUNT": "转写失败时的重试次数。",
    "STT_FAILOVER_ENABLED": "某个引擎失败后是否自动切换到下一个。",
    "STT_CACHE_ENABLED": "是否缓存转写结果以避免重复转写。",
    "STT_CACHE_TTL_S": "转写缓存的过期时间（秒）。",
    "STT_PROVIDERS": "语音转写引擎列表，按 priority 从高到低尝试。",
    # 插件
    "PLUGINS_AUTO_DISCOVERY_ENABLED": "是否自动扫描并发现插件目录中的新插件。",
    "PLUGINS_ENABLED": "是否启用插件系统。",
    "PLUGINS_LOAD_PATHS": "额外的插件搜索路径列表。",
    "PLUGINS_ALLOW": "仅允许加载的插件 ID 白名单，为空则不限制。",
    "PLUGINS_DENY": "禁止加载的插件 ID 黑名单。",
    "PLUGINS_ENTRIES": "按插件 ID 的启停与自定义配置（JSON 对象）。",
    # 技能
    "SKILLS_ENABLED": "是否启用技能系统。",
    "SKILLS_ENTRIES": "按技能 key 的启停与自定义配置（JSON 对象）。",
    "SKILLS_LOAD_EXTRA_DIRS": "额外的技能搜索目录列表。",
    "SKILLS_INSTALL_NODE_MANAGER": "安装 Node.js 依赖时使用的包管理器（npm/yarn/pnpm）。",
    "SKILLS_INSTALL_PREFER_BREW": "macOS 上安装系统依赖时优先使用 Homebrew。",
    "SKILLS_INSTALL_TIMEOUT_MS": "技能安装操作的超时时间（毫秒）。",
    "SKILLS_SECURITY_ALLOWED_DOWNLOAD_DOMAINS": "技能安装允许下载资源的域名白名单。",
    "SKILLS_LIMIT_MAX_IN_PROMPT": "单次 Prompt 中注入的最大技能数量。",
    "SKILLS_LIMIT_MAX_PROMPT_CHARS": "技能注入 Prompt 的最大总字符数。",
    "SKILLS_LIMIT_MAX_FILE_BYTES": "单个技能文件的最大字节数。",
    # 日志
    "LOGGING": "日志系统配置（级别、目录、分段、保留策略等，JSON 对象）。",
    # WebUI
    "WEBUI_ENABLED": "是否启用 WebUI 管理界面。",
    "WEBUI_HOST": "WebUI 监听的网络地址，0.0.0.0 表示所有接口。",
    "WEBUI_PORT": "WebUI 监听的端口号。",
    "WEBUI_TOKEN": "访问 WebUI 所需的认证令牌。",
    "WEBUI_OWNER_USER_ID": "WebUI 管理员的用户 ID。",
    # MCP
    "MCP": "MCP 运行时配置（服务器列表、重载策略、超时等，JSON 对象）。",
    # 存储与路径
    "AGENTS_DEFAULTS": "多 Agent 的默认配置（如 workspace 等，JSON 对象）。",
    "AGENTS_LIST": "Agent 列表，每项可定义 id、workspace 等属性。",
    "WORKSPACE_PATH": "主工作区的文件系统路径。",
    "SESSIONS_DIR": "会话数据的存储目录。",
    "VECTOR_DB_PATH": "向量数据库的存储路径。",
    "CONTEXT_ENGINE": "上下文引擎类型（vector 或其他）。",
    "EMBEDDING_MODEL": "文本嵌入使用的模型名称。",
    "EMBEDDING_API_KEY": "嵌入模型服务的 API 密钥。",
    "EMBEDDING_API_BASE": "嵌入模型的 API 地址，留空使用默认。",
    "MEMORY_SEARCH_LIMIT": "每次记忆检索返回的最大条目数。",
    "MEMORY_VECTOR_WEIGHT": "记忆排序中向量相似度的权重（0-1）。",
    "MEMORY_TEXT_WEIGHT": "记忆排序中文本匹配的权重（0-1）。",
    "MEMORY_MMR_LAMBDA": "MMR 多样性系数，越大结果越相关，越小越多样（0-1）。",
    "MEMORY_TEMPORAL_HALF_LIFE_DAYS": "记忆时间衰减的半衰期天数，越小越偏好新记忆。",
    "MEMORY_INCLUDE_SESSIONS": "是否将历史会话消息纳入记忆检索。",
    "MEMORY_SESSIONS_MAX_MESSAGES": "纳入记忆的历史会话最大消息条数。",
    # 子体系统
    "NODE_ENABLED": "是否启用子体（远程节点）系统。",
    "NODE_HOST": "子体服务监听的网络地址。",
    "NODE_TOKENS": "子体节点的认证令牌映射（JSON 对象）。",
    "SUBAGENT_WS_PORT": "子体 WebSocket 通信端口。",
    # 心跳
    "HEARTBEAT_ENABLED": "是否启用定时心跳自省任务。",
    "HEARTBEAT_INTERVAL_S": "心跳自省的执行间隔（秒）。",
    # 工具与安全
    "BRAVE_API_KEY": "Brave 搜索引擎的 API 密钥。",
    "EXEC_TIMEOUT": "系统命令执行的超时时间（秒）。",
    "RESTRICT_TO_WORKSPACE": "是否限制文件操作只能在工作区目录内执行。",
    "GIT_USERNAME": "Git 操作使用的用户名。",
    "GIT_TOKEN": "Git 操作使用的认证令牌。",
    "MEDIA_UNDERSTANDING": "多媒体理解配置（图片/音频/视频/文件，JSON 对象）。",
    "OWNER_QQ": "机器人主人的 QQ 号码。",
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

