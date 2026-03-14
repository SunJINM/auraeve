"""工具策略引擎数据契约。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PolicyContext:
    """工具策略评估的上下文输入。"""
    tool_name: str
    args: dict
    session_id: str
    channel: str | None = None
    chat_id: str | None = None
    is_subagent: bool = False
    tool_group: str | None = None
    plugin_id: str | None = None
    mcp_server: str | None = None
    tool_metadata: dict | None = None


@dataclass
class PolicyDecision:
    """单层策略的决策记录（用于审计追踪）。"""
    layer: str          # global / session / subagent
    rule_id: str        # 命中的规则标识
    allowed: bool
    reason: str
    rewritten_args: dict | None = None


@dataclass
class PolicyResult:
    """策略引擎最终输出。"""
    allowed: bool
    reason: str
    rewritten_args: dict            # 经改写的参数（无改写时等于原始 args）
    trace: list[PolicyDecision] = field(default_factory=list)
