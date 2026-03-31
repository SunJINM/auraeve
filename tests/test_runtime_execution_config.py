from __future__ import annotations

import unittest

from auraeve.agent_runtime.budget import (
    ExecutionBudget,
    RuntimeExecutionConfig,
    normalize_runtime_execution_config,
)
from auraeve.config.defaults import DEFAULTS
from auraeve.config.schema import normalize_config_object, validate_config_object


class RuntimeExecutionConfigTests(unittest.TestCase):
    def test_default_session_subagent_concurrency_is_eight(self) -> None:
        self.assertEqual(DEFAULTS["MAX_SESSION_SUBAGENT_CONCURRENT"], 8)

    def test_validate_runtime_execution_shape(self) -> None:
        payload = dict(DEFAULTS)
        payload["RUNTIME_EXECUTION"] = {"maxTurns": "64"}
        ok, issues = validate_config_object(payload)
        self.assertFalse(ok)
        self.assertTrue(any(i.get("path") == "RUNTIME_EXECUTION.maxTurns" for i in issues))

    def test_validate_runtime_loop_guard_enum(self) -> None:
        payload = dict(DEFAULTS)
        payload["RUNTIME_LOOP_GUARD"] = {"onRepeat": "invalid"}
        ok, issues = validate_config_object(payload)
        self.assertFalse(ok)
        self.assertTrue(any(i.get("path") == "RUNTIME_LOOP_GUARD.onRepeat" for i in issues))

    def test_normalize_runtime_execution_partial_merge(self) -> None:
        payload = dict(DEFAULTS)
        payload["RUNTIME_EXECUTION"] = {"maxTurns": 10}
        normalized = normalize_config_object(payload)
        runtime_execution = normalized["RUNTIME_EXECUTION"]
        self.assertEqual(runtime_execution["maxTurns"], 10)
        self.assertIn("toolConcurrency", runtime_execution)

    def test_budget_admit_and_consume(self) -> None:
        cfg = RuntimeExecutionConfig(
            max_turns=5,
            max_tool_calls_total=5,
            max_tool_calls_per_turn=3,
            max_wall_time_ms=10000,
            max_recovery_attempts=1,
            tool_concurrency=2,
            tool_timeout_ms=1000,
            tool_failure_policy="best_effort",
        )
        budget = ExecutionBudget(cfg)
        budget.mark_turn_started()
        self.assertEqual(budget.admit_tool_calls(10), 3)
        budget.consume_tool_calls(3)
        self.assertEqual(budget.admit_tool_calls(10), 2)

    def test_runtime_execution_normalization_with_fallback(self) -> None:
        cfg = normalize_runtime_execution_config({"maxTurns": 8}, fallback_max_turns=20)
        self.assertEqual(cfg.max_turns, 8)
        cfg2 = normalize_runtime_execution_config(None, fallback_max_turns=20)
        self.assertEqual(cfg2.max_turns, 20)


if __name__ == "__main__":
    unittest.main()
