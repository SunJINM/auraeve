"""工具策略引擎：3 层分级判定 + 可追踪决策 trace。

层次（从外到内）：
  global   → 系统级禁用工具列表（跨所有会话）
  session  → 按渠道/chat_id 配置的允许/拒绝规则
  subagent → 子代理专属限制（禁止递归派生、收紧高风险工具）
"""

from __future__ import annotations

from loguru import logger

from .contracts import PolicyContext, PolicyDecision, PolicyResult

# 子代理禁止使用的工具（防止无限递归派生）
_SUBAGENT_DENY: frozenset[str] = frozenset({"agent"})

# 高副作用工具风险标签（用于 session 层策略参考）
_HIGH_RISK_TOOLS: frozenset[str] = frozenset({
    "exec", "write_file", "edit_file", "browser",
})


class ToolPolicyEngine:
    """
    工具策略引擎。

    参数：
        is_subagent:     是否为子代理上下文（触发第 3 层限制）
        global_deny:     全局禁用工具名集合
        session_policy:  按渠道的会话级策略，格式：
                         { channel_name: {"deny": [...], "allow": [...], "group_deny": [...], "group_allow": [...] } }
    """

    def __init__(
        self,
        is_subagent: bool = False,
        global_deny: set[str] | None = None,
        session_policy: dict[str, dict] | None = None,
    ) -> None:
        self._is_subagent = is_subagent
        self._global_deny: frozenset[str] = frozenset(global_deny or set())
        self._session_policy: dict[str, dict] = session_policy or {}

    @staticmethod
    def infer_tool_group(tool_name: str) -> str:
        if tool_name.startswith("mcp_"):
            return "mcp"
        if tool_name in {"read_file", "write_file", "edit_file", "list_dir"}:
            return "filesystem"
        if tool_name in {"web_search", "web_fetch", "browser"}:
            return "web"
        if tool_name in {"agent", "message", "todo", "cron"}:
            return "agent"
        if tool_name in {"exec"}:
            return "shell"
        return "general"

    @staticmethod
    def infer_mcp_server(tool_name: str) -> str | None:
        return None

    async def evaluate(self, ctx: PolicyContext) -> PolicyResult:
        """对一次工具调用执行分层策略判定，返回 PolicyResult。"""
        trace: list[PolicyDecision] = []
        rewritten_args = dict(ctx.args)

        tool_group = ctx.tool_group or self.infer_tool_group(ctx.tool_name)
        meta_mcp = {}
        if isinstance(ctx.tool_metadata, dict):
            mcp_raw = ctx.tool_metadata.get("mcp")
            if isinstance(mcp_raw, dict):
                meta_mcp = mcp_raw
        mcp_server = (
            ctx.mcp_server
            or str(meta_mcp.get("server_id") or "").strip()
            or self.infer_mcp_server(ctx.tool_name)
        ) or None

        # ── 层 1：全局策略 ────────────────────────────────────────────────
        if ctx.tool_name in self._global_deny:
            decision = PolicyDecision(
                layer="global",
                rule_id="global_deny_list",
                allowed=False,
                reason=f"全局策略：工具 '{ctx.tool_name}' 已被禁用",
            )
            trace.append(decision)
            logger.info(f"[policy] {ctx.tool_name} 被全局策略拒绝（session={ctx.session_id}）")
            return PolicyResult(
                allowed=False,
                reason=decision.reason,
                rewritten_args=rewritten_args,
                trace=trace,
            )
        trace.append(PolicyDecision(
            layer="global", rule_id="global_allow", allowed=True, reason="通过全局策略"
        ))

        # ── 层 2：会话策略 ────────────────────────────────────────────────
        if ctx.tool_name in _HIGH_RISK_TOOLS:
            trace.append(PolicyDecision(
                layer="session",
                rule_id="risk_tag:high",
                allowed=True,
                reason=f"高风险工具标记：{ctx.tool_name}",
            ))

        if ctx.channel and ctx.channel in self._session_policy:
            ch_policy = self._session_policy[ctx.channel]
            deny_list: list[str] = ch_policy.get("deny", [])
            allow_list: list[str] = ch_policy.get("allow", [])
            group_deny: list[str] = ch_policy.get("group_deny", [])
            group_allow: list[str] = ch_policy.get("group_allow", [])
            mcp_deny: list[str] = ch_policy.get("mcp_deny", [])
            mcp_allow: list[str] = ch_policy.get("mcp_allow", [])

            if ctx.tool_name in deny_list:
                decision = PolicyDecision(
                    layer="session",
                    rule_id=f"session_deny:{ctx.channel}",
                    allowed=False,
                    reason=f"渠道策略 [{ctx.channel}]：工具 '{ctx.tool_name}' 不允许使用",
                )
                trace.append(decision)
                logger.info(
                    f"[policy] {ctx.tool_name} 被会话策略拒绝"
                    f"（channel={ctx.channel}，session={ctx.session_id}）"
                )
                return PolicyResult(
                    allowed=False,
                    reason=decision.reason,
                    rewritten_args=rewritten_args,
                    trace=trace,
                )

            if allow_list and ctx.tool_name not in allow_list:
                decision = PolicyDecision(
                    layer="session",
                    rule_id=f"session_allowlist:{ctx.channel}",
                    allowed=False,
                    reason=f"渠道策略 [{ctx.channel}]：工具 '{ctx.tool_name}' 不在允许列表中",
                )
                trace.append(decision)
                return PolicyResult(
                    allowed=False,
                    reason=decision.reason,
                    rewritten_args=rewritten_args,
                    trace=trace,
                )

            if group_deny and tool_group in set(group_deny):
                decision = PolicyDecision(
                    layer="session",
                    rule_id=f"session_group_deny:{ctx.channel}",
                    allowed=False,
                    reason=f"渠道策略 [{ctx.channel}]：工具组 '{tool_group}' 被禁用",
                )
                trace.append(decision)
                return PolicyResult(
                    allowed=False,
                    reason=decision.reason,
                    rewritten_args=rewritten_args,
                    trace=trace,
                )

            if group_allow and tool_group not in set(group_allow):
                decision = PolicyDecision(
                    layer="session",
                    rule_id=f"session_group_allow:{ctx.channel}",
                    allowed=False,
                    reason=f"渠道策略 [{ctx.channel}]：工具组 '{tool_group}' 不在允许列表中",
                )
                trace.append(decision)
                return PolicyResult(
                    allowed=False,
                    reason=decision.reason,
                    rewritten_args=rewritten_args,
                    trace=trace,
                )

            if mcp_server:
                if mcp_deny and mcp_server in set(mcp_deny):
                    decision = PolicyDecision(
                        layer="session",
                        rule_id=f"session_mcp_deny:{ctx.channel}",
                        allowed=False,
                        reason=f"渠道策略 [{ctx.channel}]：MCP 服务器 '{mcp_server}' 被禁用",
                    )
                    trace.append(decision)
                    return PolicyResult(
                        allowed=False,
                        reason=decision.reason,
                        rewritten_args=rewritten_args,
                        trace=trace,
                    )
                if mcp_allow and mcp_server not in set(mcp_allow):
                    decision = PolicyDecision(
                        layer="session",
                        rule_id=f"session_mcp_allow:{ctx.channel}",
                        allowed=False,
                        reason=f"渠道策略 [{ctx.channel}]：MCP 服务器 '{mcp_server}' 不在允许列表中",
                    )
                    trace.append(decision)
                    return PolicyResult(
                        allowed=False,
                        reason=decision.reason,
                        rewritten_args=rewritten_args,
                        trace=trace,
                    )

        trace.append(PolicyDecision(
            layer="session", rule_id="session_pass", allowed=True, reason="通过会话策略"
        ))

        # ── 层 3：子代理策略 ──────────────────────────────────────────────
        if ctx.is_subagent and ctx.tool_name in _SUBAGENT_DENY:
            decision = PolicyDecision(
                layer="subagent",
                rule_id="subagent_deny_agent",
                allowed=False,
                reason=f"子代理策略：禁止在子代理内使用 '{ctx.tool_name}'（防止无限递归）",
            )
            trace.append(decision)
            logger.info(f"[policy] {ctx.tool_name} 被子代理策略拒绝（session={ctx.session_id}）")
            return PolicyResult(
                allowed=False,
                reason=decision.reason,
                rewritten_args=rewritten_args,
                trace=trace,
            )
        trace.append(PolicyDecision(
            layer="subagent", rule_id="subagent_pass", allowed=True, reason="通过子代理策略"
        ))

        return PolicyResult(
            allowed=True,
            reason="通过所有策略层",
            rewritten_args=rewritten_args,
            trace=trace,
        )
