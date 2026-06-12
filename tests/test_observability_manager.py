from __future__ import annotations

import asyncio

import pytest

from auraeve.observability.manager import ObservabilityManager, ObservabilitySettings


@pytest.mark.asyncio
async def test_volatile_event_reaches_subscribers_without_log_persistence(tmp_path) -> None:
    manager = ObservabilityManager(
        ObservabilitySettings(
            enabled=True,
            dir_path=tmp_path / "logs",
        )
    )
    _, queue = manager.subscribe(subsystems=["runtime/assistant"])

    event = manager.emit(
        level="info",
        kind="event",
        subsystem="runtime/assistant",
        message="assistant_text_delta",
        attrs={"delta": "你"},
        session_key="webui:s1",
        persist=False,
    )

    received = await asyncio.wait_for(queue.get(), timeout=1)

    assert event is not None
    assert received["message"] == "assistant_text_delta"
    assert manager.tail()["events"] == []
