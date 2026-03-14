from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger

from auraeve.providers.base import LLMProvider


@dataclass
class LongTermCandidate:
    session_key: str
    channel: str
    chat_id: str
    user_content: str
    assistant_content: str
    tools_used: list[str]
    occurred_at: datetime


class MemoryLifecycleService:
    """
    Memory lifecycle:
    - write detailed daily logs for every normal turn
    - let LLM decide whether/how to update MEMORY.md
    """

    def __init__(
        self,
        *,
        workspace: Path,
        provider: LLMProvider,
        model: str,
        timezone: str = "Asia/Shanghai",
    ) -> None:
        self._workspace = workspace
        self._provider = provider
        self._model = model
        self._timezone_name = timezone
        self._memory_dir = workspace / "memory"
        self._memory_file = self._memory_dir / "MEMORY.md"
        self._queue: asyncio.Queue[LongTermCandidate] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        self.ensure_initialized()
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("[memory] lifecycle service started")

    async def stop(self) -> None:
        self._running = False
        if self._worker_task is None:
            return
        self._worker_task.cancel()
        try:
            await self._worker_task
        except asyncio.CancelledError:
            pass
        finally:
            self._worker_task = None
        logger.info("[memory] lifecycle service stopped")

    def ensure_initialized(self) -> None:
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        if not self._memory_file.exists():
            self._memory_file.write_text(
                "# MEMORY\n\n"
                "长期记忆区：仅保留稳定、跨天仍有价值的信息。\n"
                "由系统基于对话自动维护。\n",
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
        user_text = (user_content or "").strip()
        assistant_text = (assistant_content or "").strip()
        if not user_text and not assistant_text:
            return

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

        candidate = LongTermCandidate(
            session_key=session_key,
            channel=channel,
            chat_id=chat_id,
            user_content=user_text,
            assistant_content=assistant_text,
            tools_used=tools_used or [],
            occurred_at=now,
        )
        try:
            self._queue.put_nowait(candidate)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[memory] enqueue failed: {exc}")

    def _tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self._timezone_name)
        except Exception:
            return ZoneInfo("Asia/Shanghai")

    def _today_file(self, now: datetime) -> Path:
        return self._memory_dir / f"{now.strftime('%Y-%m-%d')}.md"

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
                "## 说明\n"
                "- 本文件记录当日详细对话与执行过程。\n"
                "- 长期信息由系统另行评估写入 MEMORY.md。\n\n",
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

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                item = await self._queue.get()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[memory] worker queue error: {exc}")
                continue

            # Debounce: keep only latest pending item for long-term update.
            latest = item
            try:
                while not self._queue.empty():
                    latest = self._queue.get_nowait()
            except Exception:
                pass

            try:
                await self._maybe_update_long_term(latest)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[memory] long-term update failed: {exc}")

    async def _maybe_update_long_term(self, item: LongTermCandidate) -> None:
        current_memory = ""
        if self._memory_file.exists():
            current_memory = self._memory_file.read_text(encoding="utf-8", errors="replace")

        tools_text = ", ".join(item.tools_used) if item.tools_used else "(none)"
        payload = {
            "turn": {
                "time": item.occurred_at.isoformat(),
                "session": item.session_key,
                "channel": item.channel,
                "chat_id": item.chat_id,
                "user": item.user_content,
                "assistant": item.assistant_content,
                "tools_used": tools_text,
            },
            "current_memory": current_memory,
            "rules": {
                "update_only_if_stable": True,
                "keep_memory_concise": True,
                "drop_transient_details": True,
            },
        }
        system_prompt = (
            "你是记忆维护器。任务：判断这轮对话是否值得写入长期记忆。"
            "如果不需要更新，返回 should_update=false。"
            "如果需要，返回 should_update=true，并给出完整 updated_memory_markdown。"
            "输出必须是 JSON 对象，字段固定："
            "should_update(boolean), reason(string), updated_memory_markdown(string)。"
        )
        response = await self._provider.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            tools=None,
            model=self._model,
            temperature=0.1,
            max_tokens=1800,
        )
        parsed = self._parse_json(response.content or "")
        if not isinstance(parsed, dict):
            return
        if not bool(parsed.get("should_update")):
            return
        updated = str(parsed.get("updated_memory_markdown") or "").strip()
        if not updated:
            return
        self._memory_file.write_text(updated.rstrip() + "\n", encoding="utf-8")
        logger.info("[memory] MEMORY.md updated by llm judgement")

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any] | None:
        text = (raw or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return None
        return None
