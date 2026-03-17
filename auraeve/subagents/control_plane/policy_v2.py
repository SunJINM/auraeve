"""PolicyEngineV2：四维动作级风险策略。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from auraeve.subagents.data.models import RiskLevel


@dataclass
class PolicyContext:
    tool_name: str
    args: dict[str, Any]
    node_id: str = ""
    task_priority: int = 5
    policy_profile: str = "default"


@dataclass
class PolicyResult:
    risk_level: RiskLevel
    requires_approval: bool
    reason: str = ""
    denied: bool = False


# 工具级默认风险
_TOOL_RISK: dict[str, RiskLevel] = {
    "shell.run": RiskLevel.HIGH,
    "exec": RiskLevel.HIGH,
    "write_file": RiskLevel.MEDIUM,
    "edit_file": RiskLevel.MEDIUM,
    "browser": RiskLevel.MEDIUM,
    "fs.write": RiskLevel.MEDIUM,
    "read_file": RiskLevel.LOW,
    "fs.read": RiskLevel.LOW,
    "fs.list": RiskLevel.LOW,
    "list_dir": RiskLevel.LOW,
    "web_search": RiskLevel.LOW,
    "web_fetch": RiskLevel.LOW,
    "memory_search": RiskLevel.LOW,
    "message": RiskLevel.LOW,
    "todo": RiskLevel.LOW,
}

# 参数级危险模式
_DANGEROUS_PATTERNS = [
    "rm -rf", "format c:", "shutdown", "reboot",
    "dd if=", "mkfs", "> /dev/sd", "del /f /s /q",
]


class PolicyEngineV2:
    """四维风险评估：工具级 + 参数级 + 节点级 + 任务级。"""

    def __init__(
        self,
        production_nodes: set[str] | None = None,
        command_whitelist: list[str] | None = None,
        path_whitelist: list[str] | None = None,
    ) -> None:
        self._production_nodes = production_nodes or set()
        self._command_whitelist = command_whitelist
        self._path_whitelist = path_whitelist

    def evaluate(self, ctx: PolicyContext) -> PolicyResult:
        # L1: 工具级
        tool_risk = _TOOL_RISK.get(ctx.tool_name, RiskLevel.MEDIUM)

        # L2: 参数级提升
        param_risk = self._check_params(ctx)
        if param_risk and param_risk.value > tool_risk.value:
            tool_risk = param_risk

        # L3: 节点级提升（生产节点策略更严）
        if ctx.node_id in self._production_nodes:
            if tool_risk == RiskLevel.MEDIUM:
                tool_risk = RiskLevel.HIGH

        # L4: 任务级提升（高优先级任务更严）
        if ctx.task_priority >= 8 and tool_risk == RiskLevel.MEDIUM:
            tool_risk = RiskLevel.HIGH

        # 决策
        if tool_risk == RiskLevel.CRITICAL:
            return PolicyResult(
                risk_level=RiskLevel.CRITICAL,
                requires_approval=True,
                denied=True,
                reason="critical 级操作默认禁止",
            )
        if tool_risk == RiskLevel.HIGH:
            return PolicyResult(
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
                reason=f"工具 {ctx.tool_name} 风险等级 high",
            )
        if tool_risk == RiskLevel.MEDIUM:
            return PolicyResult(
                risk_level=RiskLevel.MEDIUM,
                requires_approval=False,
                reason=f"工具 {ctx.tool_name} 风险等级 medium，自动放行",
            )
        return PolicyResult(
            risk_level=RiskLevel.LOW,
            requires_approval=False,
        )

    def _check_params(self, ctx: PolicyContext) -> RiskLevel | None:
        cmd = ctx.args.get("cmd", "") or ctx.args.get("command", "")
        if isinstance(cmd, str):
            cmd_lower = cmd.lower()
            for pattern in _DANGEROUS_PATTERNS:
                if pattern in cmd_lower:
                    return RiskLevel.CRITICAL

            if self._command_whitelist and cmd_lower:
                if not any(cmd_lower.startswith(w) for w in self._command_whitelist):
                    return RiskLevel.HIGH

        path = ctx.args.get("path", "") or ctx.args.get("file_path", "")
        if isinstance(path, str) and self._path_whitelist and path:
            if not any(path.startswith(w) for w in self._path_whitelist):
                return RiskLevel.HIGH

        return None
