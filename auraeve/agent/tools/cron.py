"""定时任务工具：管理提醒和周期性任务。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from auraeve.agent.tools.base import Tool
from auraeve.cron.service import CronService
from auraeve.cron.types import CronSchedule


class CronTool(Tool):
    """管理提醒和周期性任务的工具。"""

    def __init__(self, cron_service: CronService):
        self._cron = cron_service
        self._channel = ""
        self._chat_id = ""

    def set_context(self, channel: str, chat_id: str) -> None:
        self._channel = channel
        self._chat_id = chat_id

    @property
    def name(self) -> str:
        return "cron"

    @property
    def description(self) -> str:
        return (
            "管理提醒和周期性任务。支持操作：\n"
            "- status：查看服务状态（任务总数、下次唤醒时间）\n"
            "- list：列出所有任务（含禁用任务）\n"
            "- add：添加新任务\n"
            "- update：启用/禁用指定任务\n"
            "- remove：删除任务\n"
            "- run：立即执行指定任务\n"
            "- runs：查看任务的最近运行记录\n"
            "- wake：查询下次自动唤醒时间"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "list", "add", "update", "remove", "run", "runs", "wake"],
                    "description": "要执行的操作"
                },
                "message": {
                    "type": "string",
                    "description": "提醒内容（add 时使用）"
                },
                "every_seconds": {
                    "type": "integer",
                    "description": "间隔秒数（用于周期性任务，add 时使用）"
                },
                "cron_expr": {
                    "type": "string",
                    "description": "Cron 表达式，如 '0 9 * * *'（add 时使用）"
                },
                "at": {
                    "type": "string",
                    "description": "一次性执行的 ISO 日期时间，如 '2026-02-12T10:30:00'（add 时使用）"
                },
                "job_id": {
                    "type": "string",
                    "description": "任务 ID（update/remove/run/runs 时使用）"
                },
                "enabled": {
                    "type": "boolean",
                    "description": "启用或禁用任务（update 时使用）"
                },
                "context_messages": {
                    "type": "array",
                    "description": "注入到任务执行时的近期对话上下文（可选，消息格式与对话历史相同）",
                    "items": {"type": "object"}
                }
            },
            "required": ["action"]
        }

    async def execute(
        self,
        action: str,
        message: str = "",
        every_seconds: int | None = None,
        cron_expr: str | None = None,
        at: str | None = None,
        job_id: str | None = None,
        enabled: bool | None = None,
        context_messages: list[dict] | None = None,
        **kwargs: Any
    ) -> str:
        if action == "status":
            return self._status()
        elif action == "list":
            return self._list_jobs()
        elif action == "add":
            return self._add_job(message, every_seconds, cron_expr, at, context_messages)
        elif action == "update":
            return self._update_job(job_id, enabled)
        elif action == "remove":
            return self._remove_job(job_id)
        elif action == "run":
            return await self._run_job(job_id)
        elif action == "runs":
            return self._runs(job_id)
        elif action == "wake":
            return self._wake()
        return f"未知操作：{action}"

    def _status(self) -> str:
        s = self._cron.status()
        next_wake = s.get("next_wake_at_ms")
        next_str = (
            datetime.fromtimestamp(next_wake / 1000).strftime("%Y-%m-%d %H:%M:%S")
            if next_wake else "无"
        )
        return (
            f"定时任务服务状态：\n"
            f"- 运行中：{s.get('enabled', False)}\n"
            f"- 任务总数：{s.get('jobs', 0)}\n"
            f"- 下次唤醒：{next_str}"
        )

    def _list_jobs(self) -> str:
        jobs = self._cron.list_jobs(include_disabled=True)
        if not jobs:
            return "暂无定时任务。"
        lines = []
        for j in jobs:
            next_run = j.state.next_run_at_ms
            next_str = (
                datetime.fromtimestamp(next_run / 1000).strftime("%Y-%m-%d %H:%M:%S")
                if next_run else "—"
            )
            status_icon = "✓" if j.enabled else "✗"
            lines.append(
                f"[{status_icon}] {j.name}（id: {j.id}，类型: {j.schedule.kind}，"
                f"下次: {next_str}，上次状态: {j.state.last_status or '—'}）"
            )
        return "定时任务列表：\n" + "\n".join(lines)

    def _add_job(
        self,
        message: str,
        every_seconds: int | None,
        cron_expr: str | None,
        at: str | None,
        context_messages: list[dict] | None,
    ) -> str:
        if not message:
            return "错误：add 操作需要提供 message"
        if not self._channel or not self._chat_id:
            return "错误：缺少会话上下文（channel/chat_id）"

        delete_after = False
        if every_seconds:
            schedule = CronSchedule(kind="every", every_ms=every_seconds * 1000)
        elif cron_expr:
            schedule = CronSchedule(kind="cron", expr=cron_expr)
        elif at:
            dt = datetime.fromisoformat(at)
            at_ms = int(dt.timestamp() * 1000)
            schedule = CronSchedule(kind="at", at_ms=at_ms)
            delete_after = True
        else:
            return "错误：必须提供 every_seconds、cron_expr 或 at 其中之一"

        # 若有上下文消息，序列化后附加到任务消息中
        effective_message = message
        if context_messages:
            ctx_json = json.dumps(context_messages, ensure_ascii=False)
            effective_message = f"{message}\n\n[context_messages]{ctx_json}[/context_messages]"

        job = self._cron.add_job(
            name=message[:30],
            schedule=schedule,
            message=effective_message,
            deliver=True,
            channel=self._channel,
            to=self._chat_id,
            delete_after_run=delete_after,
        )
        return f"已创建任务 '{job.name}'（id: {job.id}）"

    def _update_job(self, job_id: str | None, enabled: bool | None) -> str:
        if not job_id:
            return "错误：update 操作需要提供 job_id"
        if enabled is None:
            return "错误：update 操作需要提供 enabled（true/false）"
        job = self._cron.enable_job(job_id, enabled)
        if not job:
            return f"任务 {job_id} 不存在"
        state = "已启用" if enabled else "已禁用"
        return f"任务 '{job.name}'（{job_id}）{state}"

    def _remove_job(self, job_id: str | None) -> str:
        if not job_id:
            return "错误：remove 操作需要提供 job_id"
        if self._cron.remove_job(job_id):
            return f"已删除任务 {job_id}"
        return f"任务 {job_id} 不存在"

    async def _run_job(self, job_id: str | None) -> str:
        if not job_id:
            return "错误：run 操作需要提供 job_id"
        ok = await self._cron.run_job(job_id, force=True)
        if ok:
            return f"任务 {job_id} 已立即执行"
        return f"任务 {job_id} 不存在"

    def _runs(self, job_id: str | None) -> str:
        jobs = self._cron.list_jobs(include_disabled=True)
        if job_id:
            jobs = [j for j in jobs if j.id == job_id]
            if not jobs:
                return f"任务 {job_id} 不存在"
        if not jobs:
            return "暂无定时任务。"
        lines = []
        for j in jobs:
            last_run = j.state.last_run_at_ms
            last_str = (
                datetime.fromtimestamp(last_run / 1000).strftime("%Y-%m-%d %H:%M:%S")
                if last_run else "从未运行"
            )
            lines.append(
                f"{j.name}（{j.id}）：上次运行={last_str}，"
                f"状态={j.state.last_status or '—'}，"
                f"错误={j.state.last_error or '无'}"
            )
        return "任务运行记录：\n" + "\n".join(lines)

    def _wake(self) -> str:
        s = self._cron.status()
        next_wake = s.get("next_wake_at_ms")
        if not next_wake:
            return "当前无计划唤醒时间（没有启用的定时任务）"
        dt_str = datetime.fromtimestamp(next_wake / 1000).strftime("%Y-%m-%d %H:%M:%S")
        return f"下次自动唤醒：{dt_str}"
