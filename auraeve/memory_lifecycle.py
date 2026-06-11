from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from loguru import logger


CONTROL_TOKENS = {"__SILENT__", "HEARTBEAT_OK"}


class MemoryLifecycleService:
    """
    简单记忆生命周期：
    - MEMORY.md 保存少量长期记忆，由用户或助手明确编辑
    - memory/logs/YYYY-MM-DD.md 只追加普通对话日志
    """

    def __init__(
        self,
        *,
        workspace: Path,
        provider=None,
        model: str | None = None,
        timezone: str = "Asia/Shanghai",
        on_memory_file_changed: Callable[[Path], None] | None = None,
    ) -> None:
        self._workspace = workspace
        self._timezone_name = timezone
        self._memory_dir = workspace / "memory"
        self._logs_dir = self._memory_dir / "logs"
        self._memory_file = self._memory_dir / "MEMORY.md"
        self._on_memory_file_changed = on_memory_file_changed

    async def start(self) -> None:
        self.ensure_initialized()
        logger.info("[memory] simple memory service started")

    async def stop(self) -> None:
        logger.info("[memory] simple memory service stopped")

    def ensure_initialized(self) -> None:
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        if not self._memory_file.exists():
            self._memory_file.write_text(
                "# MEMORY\n\n"
                "## 长期记忆\n"
                "- 用户偏好自然口语交流。\n",
                encoding="utf-8",
            )

    async def record_turn(
        self,
        *,
        session_key: str,
        channel: str,
        chat_id: str,
        user_content: str,
        assistant_content: str,
        tools_used: list[str] | None = None,
    ) -> None:
        if channel in {"heartbeat", "system", "cron"}:
            return

        user_text = self._sanitize_content(user_content)
        assistant_text = self._sanitize_content(assistant_content)
        if not user_text and not assistant_text:
            return

        self.ensure_initialized()
        now = datetime.now(self._tz())
        self._append_daily_entry(
            session_key=session_key,
            channel=channel,
            chat_id=chat_id,
            occurred_at=now,
            user_content=user_text,
            assistant_content=assistant_text,
            tools_used=tools_used or [],
        )

    def _sanitize_content(self, content: str | None) -> str:
        text = str(content or "").replace("\r\n", "\n").strip()
        if not text:
            return ""
        if text in CONTROL_TOKENS:
            return ""
        lines = [line for line in text.split("\n") if line.strip() not in CONTROL_TOKENS]
        return "\n".join(lines).strip()

    def _tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self._timezone_name)
        except Exception:
            return ZoneInfo("Asia/Shanghai")

    def _today_file(self, now: datetime) -> Path:
        return self._logs_dir / f"{now.strftime('%Y-%m-%d')}.md"

    def _append_daily_entry(
        self,
        *,
        session_key: str,
        channel: str,
        chat_id: str,
        occurred_at: datetime,
        user_content: str,
        assistant_content: str,
        tools_used: list[str],
    ) -> None:
        day_file = self._today_file(occurred_at)
        if not day_file.exists():
            day_file.write_text(
                f"# {occurred_at.strftime('%Y-%m-%d')}\n\n"
                "## 对话日志\n"
                "- 本文件只追加普通对话记录，不自动晋升为长期记忆。\n\n",
                encoding="utf-8",
            )

        tool_lines = "\n".join(f"- {name}" for name in tools_used) if tools_used else "- (none)"
        chunk = (
            f"## {occurred_at.strftime('%H:%M:%S')} | {channel}/{chat_id}\n"
            f"- session: `{session_key}`\n"
            f"- tools:\n{tool_lines}\n\n"
            "### User\n"
            f"{user_content or '(empty)'}\n\n"
            "### Assistant\n"
            f"{assistant_content or '(empty)'}\n\n"
        )
        with day_file.open("a", encoding="utf-8") as f:
            f.write(chunk)

        if self._on_memory_file_changed is not None:
            try:
                self._on_memory_file_changed(day_file)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[memory] change notify failed: {exc}")
