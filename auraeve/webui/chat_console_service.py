"""聊天控制台聚合服务：为聊天页提供运行面板所需的快照数据。"""
from __future__ import annotations

from typing import Any

from auraeve.subagents.data.repositories import SubagentStore
from auraeve.webui.chat_service import ChatService


class ChatConsoleService:
    """聚合会话、工具调用与子体任务快照。"""

    def __init__(
        self,
        chat_service: ChatService,
        store: SubagentStore | None = None,
    ) -> None:
        self._chat = chat_service
        self._store = store

    def get_snapshot(self, session_key: str, limit: int = 200) -> dict[str, Any]:
        run = self._chat.get_runtime_status(session_key)
        tasks = self._list_session_tasks(session_key, limit=limit)

        summary = {
            "runningTasks": sum(1 for item in tasks if item["status"] == "running"),
            "pendingApprovals": 0,
        }

        return {
            "run": run,
            "toolCalls": [],
            "tasks": tasks,
            "approvals": [],
            "timeline": [],
            "summary": summary,
        }

    def _list_session_tasks(self, session_key: str, limit: int) -> list[dict[str, Any]]:
        if self._store is None:
            return []
        tasks = [task for task in self._store.list_tasks(limit=max(limit, 200)) if task.origin_chat_id == session_key]
        tasks.sort(key=lambda item: item.created_at, reverse=True)
        return [
            {
                "taskId": task.task_id,
                "goal": task.goal,
                "priority": task.priority,
                "status": task.status.value,
                "originChannel": task.origin_channel,
                "originChatId": task.origin_chat_id,
                "agentType": task.agent_type,
                "result": task.result[:500] if task.result else "",
                "createdAt": task.created_at,
                "updatedAt": task.completed_at or task.created_at,
            }
            for task in tasks[:limit]
        ]
