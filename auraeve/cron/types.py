"""定时任务数据类型定义。"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class CronSchedule:
    """定时任务的调度计划。"""
    kind: Literal["at", "every", "cron"]
    at_ms: int | None = None        # "at" 类型：执行时间戳（毫秒）
    every_ms: int | None = None     # "every" 类型：间隔时长（毫秒）
    expr: str | None = None         # "cron" 类型：Cron 表达式
    tz: str | None = None           # Cron 表达式的时区


@dataclass
class CronPayload:
    """任务触发时的执行内容。"""
    kind: Literal["system_event", "agent_turn"] = "agent_turn"
    message: str = ""
    deliver: bool = False           # 是否将结果发送给用户
    channel: str | None = None
    to: str | None = None


@dataclass
class CronJobState:
    """任务的运行时状态。"""
    next_run_at_ms: int | None = None
    last_run_at_ms: int | None = None
    last_status: Literal["ok", "error", "skipped"] | None = None
    last_error: str | None = None


@dataclass
class CronJob:
    """一个定时任务。"""
    id: str
    name: str
    enabled: bool = True
    schedule: CronSchedule = field(default_factory=lambda: CronSchedule(kind="every"))
    payload: CronPayload = field(default_factory=CronPayload)
    state: CronJobState = field(default_factory=CronJobState)
    created_at_ms: int = 0
    updated_at_ms: int = 0
    delete_after_run: bool = False  # 一次性任务执行后是否自动删除


@dataclass
class CronStore:
    """定时任务的持久化存储结构。"""
    version: int = 1
    jobs: list[CronJob] = field(default_factory=list)
