import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from auraeve.runtime_runner import AppRuntimeRunner


@pytest.mark.asyncio
async def test_runtime_runner_shutdown_sets_restart_and_cancels_gather_task(tmp_path: Path) -> None:
    runner = AppRuntimeRunner(
        agent=MagicMock(stop=MagicMock()),
        cron_service=MagicMock(stop=MagicMock()),
        heartbeat=MagicMock(stop=MagicMock()),
        bus=MagicMock(stop=MagicMock()),
        channel_runtime=MagicMock(stop_all=AsyncMock()),
        pid_file=tmp_path / "auraeve.pid",
    )
    runner._gather_task = asyncio.create_task(asyncio.sleep(10))

    await runner.shutdown(restart=True)

    assert runner.restart_requested is True
    runner.agent.stop.assert_called_once()
    runner.cron_service.stop.assert_called_once()
    runner.heartbeat.stop.assert_called_once()
    runner.bus.stop.assert_called_once()
    assert runner._gather_task.cancelled() is True


@pytest.mark.asyncio
async def test_runtime_runner_run_starts_and_cleans_services(tmp_path: Path) -> None:
    pid_file = tmp_path / "auraeve.pid"
    pid_file.write_text("123")
    memory_lifecycle = MagicMock(start=AsyncMock(), stop=AsyncMock())
    agent = MagicMock(
        scheduler=MagicMock(start=AsyncMock(), stop=AsyncMock()),
        memory_lifecycle=memory_lifecycle,
        close_mcp=AsyncMock(),
    )
    cron_service = MagicMock(start=AsyncMock(), stop=MagicMock())
    heartbeat = MagicMock(start=AsyncMock(), stop=MagicMock())
    bus = MagicMock(stop=MagicMock())
    bus.dispatch_outbound = AsyncMock(side_effect=asyncio.CancelledError())
    channel_runtime = MagicMock(channel_tasks={}, stop_all=AsyncMock())
    channel_runtime.start_unmanaged_channel_tasks = MagicMock()

    runner = AppRuntimeRunner(
        agent=agent,
        cron_service=cron_service,
        heartbeat=heartbeat,
        bus=bus,
        channel_runtime=channel_runtime,
        pid_file=pid_file,
    )

    await runner.run()

    cron_service.start.assert_awaited_once()
    heartbeat.start.assert_awaited_once()
    agent.scheduler.start.assert_awaited_once()
    memory_lifecycle.start.assert_awaited_once()
    channel_runtime.start_unmanaged_channel_tasks.assert_called_once()
    memory_lifecycle.stop.assert_awaited_once()
    agent.scheduler.stop.assert_awaited_once()
    agent.close_mcp.assert_awaited_once()
    channel_runtime.stop_all.assert_awaited_once()
    bus.stop.assert_called()
    assert not pid_file.exists()


def test_main_no_longer_embeds_shutdown_state_machine() -> None:
    result = subprocess.run(
        ["rg", "-n", "_gather_task|async def _shutdown", "main.py"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
