from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from loguru import logger

from auraeve.providers.base import LLMProvider


CONTROL_TOKENS = {"__SILENT__", "HEARTBEAT_OK"}


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
        on_memory_file_changed: Callable[[Path], None] | None = None,
    ) -> None:
        self._workspace = workspace
        self._provider = provider
        self._model = model
        self._timezone_name = timezone
        self._memory_dir = workspace / "memory"
        self._memory_file = self._memory_dir / "MEMORY.md"
        self._audit_dir = self._memory_dir / ".audit"
        self._audit_file = self._audit_dir / "long_term_patch.log"
        self._queue: asyncio.Queue[LongTermCandidate] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._running = False
        self._on_memory_file_changed = on_memory_file_changed

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
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        if not self._memory_file.exists():
            self._memory_file.write_text(
                "# MEMORY\n\n"
                "## Facts\n"
                "- [identity] 用户偏好自然口语交流。\n",
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
        if self._on_memory_file_changed is not None:
            try:
                self._on_memory_file_changed(day_file)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[memory] dirty notify failed: {exc}")

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
            "如果需要，返回 should_update=true，并给出 operations 数组。"
            "输出必须是 JSON 对象，字段固定："
            "should_update(boolean), reason(string), operations(array)。"
            "operations 的每一项格式："
            "{op: add|update|remove, key: string, content?: string}。"
            "不要返回整篇 markdown。"
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
        ops = parsed.get("operations")
        if not isinstance(ops, list) or not ops:
            return
        updated = self._apply_patch_operations(current_memory, ops)
        if not updated:
            return

        self._memory_file.write_text(updated, encoding="utf-8")
        if self._on_memory_file_changed is not None:
            try:
                self._on_memory_file_changed(self._memory_file)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[memory] dirty notify failed: {exc}")

        reason = str(parsed.get("reason") or "").strip()
        self._append_audit_log(
            item=item,
            reason=reason,
            operations=ops,
            before=current_memory,
            after=updated,
        )
        logger.info("[memory] MEMORY.md updated by patch operations")

    def _append_audit_log(
        self,
        *,
        item: LongTermCandidate,
        reason: str,
        operations: list[Any],
        before: str,
        after: str,
    ) -> None:
        try:
            self._audit_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "time": datetime.now(self._tz()).isoformat(),
                "session": item.session_key,
                "channel": item.channel,
                "chat_id": item.chat_id,
                "reason": reason,
                "operations": operations,
                "before_sha256": hashlib.sha256(before.encode("utf-8", errors="replace")).hexdigest(),
                "after_sha256": hashlib.sha256(after.encode("utf-8", errors="replace")).hexdigest(),
            }
            with self._audit_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[memory] audit log append failed: {exc}")

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

    @staticmethod
    def _parse_memory_items(markdown: str) -> dict[str, str]:
        items: dict[str, str] = {}
        for line in (markdown or "").splitlines():
            line = line.strip()
            if not line.startswith("- [") or "] " not in line:
                continue
            try:
                key = line.split("- [", 1)[1].split("]", 1)[0].strip()
                content = line.split("] ", 1)[1].strip()
            except Exception:
                continue
            if key and content:
                items[key] = content
        return items

    @staticmethod
    def _render_memory_items(items: dict[str, str]) -> str:
        lines = ["# MEMORY", "", "## Facts"]
        for key in sorted(items):
            lines.append(f"- [{key}] {items[key]}")
        lines.append("")
        return "\n".join(lines)

    def _apply_patch_operations(self, current_markdown: str, ops: list[Any]) -> str | None:
        items = self._parse_memory_items(current_markdown)
        changed = False
        for op in ops:
            if not isinstance(op, dict):
                continue
            action = str(op.get("op") or "").strip().lower()
            key = str(op.get("key") or "").strip()
            if not key:
                continue
            if action == "remove":
                if key in items:
                    items.pop(key, None)
                    changed = True
                continue
            if action not in {"add", "update"}:
                continue
            content = str(op.get("content") or "").strip()
            if not content:
                continue
            if items.get(key) != content:
                items[key] = content
                changed = True
        if not changed:
            return None
        return self._render_memory_items(items)
