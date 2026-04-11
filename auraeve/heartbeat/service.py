"""心跳服务：定期唤醒 Agent 检查待处理任务。"""

import asyncio
from pathlib import Path
from typing import Any, Callable, Coroutine

from loguru import logger

DEFAULT_HEARTBEAT_INTERVAL_S = 30 * 60  # 默认 30 分钟

HEARTBEAT_PROMPT = """现在是你的后台心跳时间。

只读取工作区的 HEARTBEAT.md。

- 如果其中有明确待处理事项，就处理它们；只有确实值得打扰主人时，才主动联系主人
- 如果没有待处理事项，或都不值得打扰，就只回复 HEARTBEAT_OK

如果HEARTBEAT.md 中没有要求，就不要读取 memory/MEMORY.md、每日笔记、计划文件，也不要做额外搜索。"""

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


def _normalize_heartbeat_text(content: str | None) -> str:
    if not content:
        return ""
    return content.replace("\r\n", "\n").strip()


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

    @property
    def template_heartbeat_file(self) -> Path:
        return Path(__file__).resolve().parents[2] / "workspace" / "HEARTBEAT.md"

    def _read_heartbeat_file(self) -> str | None:
        if self.heartbeat_file.exists():
            try:
                return self.heartbeat_file.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    def _read_template_heartbeat_file(self) -> str | None:
        if self.template_heartbeat_file.exists():
            try:
                return self.template_heartbeat_file.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    def _is_template_heartbeat(self, content: str | None) -> bool:
        template_content = self._read_template_heartbeat_file()
        if template_content is None:
            return False
        return _normalize_heartbeat_text(content) == _normalize_heartbeat_text(template_content)

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
        heartbeat_content = self._read_heartbeat_file()
        if _is_heartbeat_empty(heartbeat_content):
            logger.info("心跳：HEARTBEAT.md 为空，跳过模型调用")
            return
        if self._is_template_heartbeat(heartbeat_content):
            logger.info("心跳：HEARTBEAT.md 与模板一致，跳过模型调用")
            return
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
        heartbeat_content = self._read_heartbeat_file()
        if _is_heartbeat_empty(heartbeat_content):
            return HEARTBEAT_OK_TOKEN
        if self._is_template_heartbeat(heartbeat_content):
            return HEARTBEAT_OK_TOKEN
        if self.on_heartbeat:
            return await self.on_heartbeat(HEARTBEAT_PROMPT)
        return None
