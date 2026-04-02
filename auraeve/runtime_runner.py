from __future__ import annotations

import asyncio
from pathlib import Path

from loguru import logger


class AppRuntimeRunner:
    def __init__(
        self,
        *,
        agent,
        cron_service,
        heartbeat,
        bus,
        channel_runtime,
        webui_server=None,
        webui_channel=None,
        subagent_ws_server=None,
        pid_file: Path | None = None,
        on_engine_cleanup=None,
    ) -> None:
        self.agent = agent
        self.cron_service = cron_service
        self.heartbeat = heartbeat
        self.bus = bus
        self.channel_runtime = channel_runtime
        self.webui_server = webui_server
        self.webui_channel = webui_channel
        self.subagent_ws_server = subagent_ws_server
        self.pid_file = pid_file
        self.on_engine_cleanup = on_engine_cleanup
        self.restart_requested = False
        self._gather_task: asyncio.Task | None = None

    async def shutdown(self, restart: bool = False) -> None:
        self.restart_requested = self.restart_requested or restart
        self.agent.stop()
        self.cron_service.stop()
        self.heartbeat.stop()
        self.bus.stop()
        if self.webui_server:
            await self.webui_server.stop()
        if self.subagent_ws_server:
            await self.subagent_ws_server.stop()
        if self._gather_task and not self._gather_task.done():
            self._gather_task.cancel()
            try:
                await self._gather_task
            except (asyncio.CancelledError, Exception):
                pass

    async def run(self) -> None:
        await self.cron_service.start()
        await self.heartbeat.start()
        await self.agent.scheduler.start()
        if self.agent.memory_lifecycle is not None:
            await self.agent.memory_lifecycle.start()

        try:
            self.channel_runtime.start_unmanaged_channel_tasks()
            tasks = [
                self.bus.dispatch_outbound(),
                *self.channel_runtime.channel_tasks.values(),
            ]
            if self.subagent_ws_server:
                tasks.append(self.subagent_ws_server.start())
            if self.webui_server:
                tasks.append(self.webui_server.start())
            if self.webui_channel:
                tasks.append(self.webui_channel.start())
            self._gather_task = asyncio.ensure_future(asyncio.gather(*tasks))
            await self._gather_task
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("?..")
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        self.cron_service.stop()
        self.heartbeat.stop()
        if self.agent.memory_lifecycle is not None:
            await self.agent.memory_lifecycle.stop()
        await self.agent.scheduler.stop()
        if self.on_engine_cleanup is not None:
            await self.on_engine_cleanup()
        await self.agent.close_mcp()
        await self.channel_runtime.stop_all()
        if self.webui_channel:
            await self.webui_channel.stop()
        if self.webui_server:
            await self.webui_server.stop()
        if self.subagent_ws_server:
            await self.subagent_ws_server.stop()
        self.bus.stop()
        if self.pid_file is not None:
            self.pid_file.unlink(missing_ok=True)
        logger.info("auraeve stopped.")
