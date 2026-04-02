"""聊天控制台聚合服务：为聊天页提供运行面板所需的快照数据。"""
from __future__ import annotations

import json
from typing import Any

from auraeve.subagents.data.repositories import SubagentStore
from auraeve.webui.chat_service import ChatService


class ChatConsoleService:
    """聚合会话、工具调用与子体任务快照。"""

    def __init__(self, chat_service: ChatService, store: SubagentStore | None = None) -> None:
        self._chat = chat_service
        self._store = store

    def get_snapshot(self, session_key: str, limit: int = 200) -> dict[str, Any]:
        session = self._chat._sm.get_or_create(session_key)
        run = self._chat.get_runtime_status(session_key)

        tool_calls = self._extract_tool_calls(session.messages)
        tasks = self._list_session_tasks(session_key, limit=limit)

        summary = {
            "runningTasks": sum(1 for item in tasks if item["status"] == "running"),
            "pendingApprovals": 0,
            "toolCalls": len(tool_calls),
            "onlineNodes": 0,
        }

        return {
            "run": run,
            "toolCalls": tool_calls,
            "tasks": tasks,
            "approvals": [],
            "nodes": [],
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

    @staticmethod
    def _extract_tool_calls(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        tool_results: dict[str, str] = {}
        items: list[dict[str, Any]] = []
        for message in messages:
            if message.get("role") == "tool":
                tool_results[str(message.get("tool_call_id") or "")] = str(message.get("content") or "")

        for message in messages:
            if message.get("role") != "assistant":
                continue
            for tool_call in message.get("tool_calls") or []:
                function = tool_call.get("function") or {}
                tool_call_id = str(tool_call.get("id") or "")
                raw_args = function.get("arguments") or ""
                try:
                    parsed_args = json.loads(raw_args) if isinstance(raw_args, str) and raw_args else raw_args
                except Exception:
                    parsed_args = raw_args
                result_preview = tool_results.get(tool_call_id, "")
                items.append(
                    {
                        "toolCallId": tool_call_id,
                        "toolName": function.get("name") or "",
                        "arguments": parsed_args,
                        "status": "completed" if tool_call_id in tool_results else "running",
                        "resultPreview": result_preview[:300],
                    }
                )
        items.reverse()
        return items
