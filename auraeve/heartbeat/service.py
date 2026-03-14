"""心跳服务：定期唤醒 Agent 检查待处理任务。"""

import asyncio
from pathlib import Path
from typing import Any, Callable, Coroutine

from loguru import logger

DEFAULT_HEARTBEAT_INTERVAL_S = 30 * 60  # 默认 30 分钟

HEARTBEAT_PROMPT = """现在是你的后台心跳时间。按顺序做以下几件事，然后判断要不要主动联系主人。

## 检查清单

1. **HEARTBEAT.md** — 读取工作区的 HEARTBEAT.md，有待处理任务就执行
2. **搁置的事项** — 读取 memory/MEMORY.md，找出主人说过"以后再说""暂时搁置""下次再看"之类的内容，如果已经超过 3 天，考虑主动跟进
3. **未完成的讨论** — grep 今天和昨天的每日笔记（memory/YYYY-MM-DD.md），找有没有没有结论的话题或 Action Item
4. **Obsidian 今日计划** — 用 MCP 工具读取今天的计划文件（计划/2026/月/今天日期.md），有未完成的 - [ ] 任务就提醒主人
5. **时间节点** — 现在是否接近主人通常的工作开始或结束时间？有没有需要提醒的事？

## 判断标准

- 发现值得告知主人的内容 → 调用 message 工具主动发送，内容简洁，一次不超过 3 条
- 没有值得打扰主人的内容 → 只回复 HEARTBEAT_OK，保持安静

## 原则

宁可少说，不要刷屏。不确定主人是否关心就不说。只有真正值得的事才开口。"""

HEARTBEAT_OK_TOKEN = "HEARTBEAT_OK"


def _is_heartbeat_empty(content: str | None) -> bool:
    """检查 HEARTBEAT.md 是否没有可执行内容。"""
    if not content:
        return True
    skip_patterns = {"- [ ]", "* [ ]", "- [x]", "* [x]"}
    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("<!--") or line in skip_patterns:
            continue
        return False
    return True


class HeartbeatService:
    """
    定期心跳服务，唤醒 Agent 检查待处理任务。

    每隔 interval_s 秒读取 workspace/HEARTBEAT.md，若有内容则触发 Agent 处理。
    """

    def __init__(
        self,
        workspace: Path,
        on_heartbeat: Callable[[str], Coroutine[Any, Any, str]] | None = None,
        interval_s: int = DEFAULT_HEARTBEAT_INTERVAL_S,
        enabled: bool = True,
    ):
        self.workspace = workspace
        self.on_heartbeat = on_heartbeat
        self.interval_s = interval_s
        self.enabled = enabled
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def heartbeat_file(self) -> Path:
        return self.workspace / "HEARTBEAT.md"

    def _read_heartbeat_file(self) -> str | None:
        if self.heartbeat_file.exists():
            try:
                return self.heartbeat_file.read_text()
            except Exception:
                return None
        return None

    async def start(self) -> None:
        if not self.enabled:
            logger.info("心跳服务已禁用")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"心跳服务已启动（间隔 {self.interval_s} 秒）")

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.interval_s)
                if self._running:
                    await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳服务出错：{e}")

    async def _tick(self) -> None:
        logger.info("心跳：主动感知中...")
        if self.on_heartbeat:
            try:
                response = await self.on_heartbeat(HEARTBEAT_PROMPT)
                if HEARTBEAT_OK_TOKEN.replace("_", "") in response.upper().replace("_", ""):
                    logger.info("心跳：安静（无需打扰主人）")
                else:
                    logger.info("心跳：已主动联系主人")
            except Exception as e:
                logger.error(f"心跳任务执行失败：{e}")

    async def trigger_now(self) -> str | None:
        if self.on_heartbeat:
            return await self.on_heartbeat(HEARTBEAT_PROMPT)
        return None
