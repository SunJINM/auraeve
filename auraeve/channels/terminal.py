"""终端渠道：通过 stdin/stdout 与 Agent 交互，用于本地调试。"""

import asyncio
import sys
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.bus.events import OutboundMessage
from auraeve.channels.base import BaseChannel


@dataclass
class TerminalConfig:
    sender_id: str = "local"
    chat_id: str = "terminal"
    allow_from: list[str] = field(default_factory=list)


class TerminalChannel(BaseChannel):
    """从 stdin 读取输入，将 Agent 回复输出到 stdout。"""

    name = "terminal"

    def __init__(self, config: TerminalConfig, command_queue: RuntimeCommandQueue):
        super().__init__(config, command_queue)
        self._task: asyncio.Task | None = None
        # Agent 回复完毕后置位，_read_loop 等待后再读下一条输入
        self._reply_ready = asyncio.Event()
        self._reply_ready.set()  # 初始状态：可以输入

    async def start(self) -> None:
        self._running = True
        print("\n── 终端调试模式 ── 输入消息后回车发送，Ctrl+C 退出 ──\n", flush=True)
        self._task = asyncio.create_task(self._read_loop())
        await self._task

    async def stop(self) -> None:
        self._running = False
        self._reply_ready.set()  # 解除可能的等待
        if self._task and not self._task.done():
            self._task.cancel()

    async def send(self, msg: OutboundMessage) -> None:
        """将 Agent 回复打印到终端，并允许读下一条输入。"""
        print(f"\n🤖 {msg.content}", flush=True)
        if msg.file_path:
            print(f"   📎 文件：{msg.file_path}", flush=True)
        if msg.image_url:
            print(f"   🖼  图片：{msg.image_url}", flush=True)
        print(flush=True)
        self._reply_ready.set()

    async def _read_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while self._running:
            # 等待上一条消息的回复完成后，再提示输入
            await self._reply_ready.wait()

            try:
                line: str = await loop.run_in_executor(None, self._read_line)
            except (EOFError, KeyboardInterrupt):
                break

            text = line.strip()
            if not text:
                continue

            # 标记"等待回复中"，阻止提前打印下一个提示符
            self._reply_ready.clear()
            print("\n⏳ 处理中...\n", flush=True)
            await self._handle_message(
                sender_id=self.config.sender_id,
                chat_id=self.config.chat_id,
                content=text,
            )

    def _read_line(self) -> str:
        sys.stdout.write("你: ")
        sys.stdout.flush()
        return sys.stdin.readline()
