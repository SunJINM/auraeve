"""子智能体上下文隔离。

对标 Claude Code 的 forkedAgent.ts / createSubagentContext()。
"""
from __future__ import annotations

import asyncio
import os
import secrets
from dataclasses import dataclass, field


def generate_agent_id() -> str:
    """生成 12 字符的 Agent ID。"""
    return secrets.token_hex(6)


@dataclass
class SubagentContext:
    """子智能体隔离上下文。"""
    agent_id: str
    parent_channel: str
    parent_chat_id: str
    cwd: str
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)

    def request_abort(self) -> None:
        self.abort_event.set()

    @property
    def is_aborted(self) -> bool:
        return self.abort_event.is_set()


def create_subagent_context(
    parent_channel: str,
    parent_chat_id: str,
    workspace: str = "",
    worktree_path: str = "",
) -> SubagentContext:
    cwd = worktree_path or workspace or os.getcwd()
    return SubagentContext(
        agent_id=generate_agent_id(),
        parent_channel=parent_channel,
        parent_chat_id=parent_chat_id,
        cwd=cwd,
    )
