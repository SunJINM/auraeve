"""聊天控制台聚合服务：为聊天页提供运行面板所需的快照数据。"""
from __future__ import annotations

import json
from typing import Any

from auraeve.subagents.data.repositories import SubagentDB
from auraeve.webui.chat_service import ChatService


class ChatConsoleService:
    """聚合会话、工具调用、子体任务、审批与节点快照。"""

    def __init__(self, chat_service: ChatService, db: SubagentDB | None = None) -> None:
        self._chat = chat_service
        self._db = db

    def get_snapshot(self, session_key: str, limit: int = 200) -> dict[str, Any]:
        session = self._chat._sm.get_or_create(session_key)
        run = self._chat.get_runtime_status(session_key)

        tool_calls = self._extract_tool_calls(session.messages)
        tasks = self._list_session_tasks(session_key, limit=limit)
        task_ids = {item["taskId"] for item in tasks}
        approvals = self._list_approvals(task_ids, limit=limit)
        nodes = self._list_nodes(tasks)
        timeline = self._build_timeline(task_ids, limit=limit)

        summary = {
            "runningTasks": sum(1 for item in tasks if item["status"] in {"dispatched", "running", "input_required", "paused"}),
            "pendingApprovals": sum(1 for item in approvals if item["status"] == "pending"),
            "toolCalls": len(tool_calls),
            "onlineNodes": sum(1 for item in nodes if item["isOnline"]),
        }

        return {
            "run": run,
            "toolCalls": tool_calls,
            "tasks": tasks,
            "approvals": approvals,
            "nodes": nodes,
            "timeline": timeline,
            "summary": summary,
        }

    def _list_session_tasks(self, session_key: str, limit: int) -> list[dict[str, Any]]:
        if self._db is None:
            return []
        tasks = [task for task in self._db.list_tasks(limit=max(limit, 200)) if task.origin_chat_id == session_key]
        tasks.sort(key=lambda item: item.created_at, reverse=True)
        return [
            {
                "taskId": task.task_id,
                "goal": task.goal,
                "assignedNodeId": task.assigned_node_id,
                "priority": task.priority,
                "status": task.status.value,
                "traceId": task.trace_id,
                "originChannel": task.origin_channel,
                "originChatId": task.origin_chat_id,
                "agentName": task.agent_name,
                "result": task.result[:500] if task.result else "",
                "createdAt": task.created_at,
                "updatedAt": task.updated_at,
            }
            for task in tasks[:limit]
        ]

    def _list_approvals(self, task_ids: set[str], limit: int) -> list[dict[str, Any]]:
        if self._db is None or not task_ids:
            return []
        approvals = [approval for approval in self._db.list_approvals(limit=max(limit, 200)) if approval.task_id in task_ids]
        return [
            {
                "approvalId": approval.approval_id,
                "taskId": approval.task_id,
                "actionDesc": approval.action_desc,
                "riskLevel": approval.risk_level.value,
                "status": approval.status.value,
                "decidedBy": approval.decided_by,
                "decidedAt": approval.decided_at,
                "createdAt": approval.created_at,
            }
            for approval in approvals[:limit]
        ]

    def _list_nodes(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._db is None:
            return []
        relevant_node_ids = {task["assignedNodeId"] for task in tasks if task["assignedNodeId"]}
        nodes = self._db.get_all_nodes()
        filtered = [node for node in nodes if node.node_id in relevant_node_ids or node.is_online]
        return [
            {
                "nodeId": node.node_id,
                "displayName": node.display_name,
                "platform": node.platform,
                "isOnline": node.is_online,
                "connectedAt": node.connected_at,
                "disconnectedAt": node.disconnected_at,
                "runningTasks": self._db.get_running_count(node.node_id),
            }
            for node in filtered
        ]

    def _build_timeline(self, task_ids: set[str], limit: int) -> list[dict[str, Any]]:
        if self._db is None:
            return []
        items: list[dict[str, Any]] = []
        for task_id in task_ids:
            for event in self._db.get_events(task_id):
                items.append(
                    {
                        "taskId": task_id,
                        "seq": event.seq,
                        "eventType": event.event_type,
                        "summary": self._summarize_event(event.event_type, event.payload),
                        "payload": event.payload,
                        "createdAt": event.created_at,
                    }
                )
        items.sort(key=lambda item: (item["createdAt"], item["seq"]), reverse=True)
        return items[:limit]

    @staticmethod
    def _summarize_event(event_type: str, payload: dict[str, Any]) -> str:
        if event_type == "state_change":
            return f'{payload.get("from", "-")} -> {payload.get("to", "-")}'
        if event_type == "span":
            operation = payload.get("operation") or "span"
            message = payload.get("message") or payload.get("status") or ""
            return f"{operation}: {message}".strip(": ")
        return event_type

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
