from __future__ import annotations

from auraeve.agent_runtime.kernel import RuntimeKernel


def test_sanitize_drops_mixed_silent_token_line() -> None:
    raw = "抱歉哥！再试一次～\n\n__SILENT__"
    cleaned = RuntimeKernel._sanitize_assistant_output(raw)
    assert cleaned == "抱歉哥！再试一次～"


def test_sanitize_exact_silent_becomes_none() -> None:
    assert RuntimeKernel._sanitize_assistant_output("__SILENT__") is None


def test_sanitize_exact_heartbeat_becomes_none() -> None:
    assert RuntimeKernel._sanitize_assistant_output("HEARTBEAT_OK") is None
