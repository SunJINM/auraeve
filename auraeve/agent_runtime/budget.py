from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RuntimeExecutionConfig:
    max_turns: int = 64
    max_tool_calls_total: int = 256
    max_tool_calls_per_turn: int = 16
    max_wall_time_ms: int = 15 * 60 * 1000
    max_recovery_attempts: int = 12
    tool_concurrency: int = 8
    tool_timeout_ms: int = 60_000
    tool_failure_policy: str = "best_effort"


def _as_positive_int(value: Any, fallback: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return fallback
    return value if value > 0 else fallback


def normalize_runtime_execution_config(
    raw: dict[str, Any] | None,
    *,
    fallback_max_turns: int | None = None,
) -> RuntimeExecutionConfig:
    base = RuntimeExecutionConfig()
    if fallback_max_turns is not None and fallback_max_turns > 0:
        base.max_turns = fallback_max_turns
    if not isinstance(raw, dict):
        return base

    policy = raw.get("toolFailurePolicy")
    if policy not in {"fail_fast", "best_effort", "threshold"}:
        policy = base.tool_failure_policy

    return RuntimeExecutionConfig(
        max_turns=_as_positive_int(raw.get("maxTurns"), base.max_turns),
        max_tool_calls_total=_as_positive_int(raw.get("maxToolCallsTotal"), base.max_tool_calls_total),
        max_tool_calls_per_turn=_as_positive_int(raw.get("maxToolCallsPerTurn"), base.max_tool_calls_per_turn),
        max_wall_time_ms=_as_positive_int(raw.get("maxWallTimeMs"), base.max_wall_time_ms),
        max_recovery_attempts=_as_positive_int(raw.get("maxRecoveryAttempts"), base.max_recovery_attempts),
        tool_concurrency=_as_positive_int(raw.get("toolConcurrency"), base.tool_concurrency),
        tool_timeout_ms=_as_positive_int(raw.get("toolTimeoutMs"), base.tool_timeout_ms),
        tool_failure_policy=policy,
    )


class ExecutionBudget:
    """Track per-run execution budget across turns, tools, and wall time."""

    def __init__(self, cfg: RuntimeExecutionConfig) -> None:
        self.cfg = cfg
        self.started_at = time.monotonic()
        self.turns_used = 0
        self.tool_calls_used = 0

    def check_turn_budget(self) -> tuple[bool, str | None]:
        if self.turns_used >= self.cfg.max_turns:
            return False, "max_turns_exhausted"
        elapsed_ms = int((time.monotonic() - self.started_at) * 1000)
        if elapsed_ms >= self.cfg.max_wall_time_ms:
            return False, "max_wall_time_exhausted"
        return True, None

    def mark_turn_started(self) -> None:
        self.turns_used += 1

    def admit_tool_calls(self, requested: int) -> int:
        remaining_total = max(self.cfg.max_tool_calls_total - self.tool_calls_used, 0)
        admitted = min(max(requested, 0), self.cfg.max_tool_calls_per_turn, remaining_total)
        return admitted

    def consume_tool_calls(self, executed: int) -> None:
        self.tool_calls_used += max(executed, 0)

    def snapshot(self) -> dict[str, int]:
        elapsed_ms = int((time.monotonic() - self.started_at) * 1000)
        return {
            "turnsUsed": self.turns_used,
            "toolCallsUsed": self.tool_calls_used,
            "elapsedMs": elapsed_ms,
            "maxTurns": self.cfg.max_turns,
            "maxToolCallsTotal": self.cfg.max_tool_calls_total,
            "maxWallTimeMs": self.cfg.max_wall_time_ms,
        }

