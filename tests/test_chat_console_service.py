from __future__ import annotations

from pathlib import Path

from auraeve.subagents.data.models import (
    Approval,
    ApprovalStatus,
    NodeSession,
    RiskLevel,
    Task,
    TaskBudget,
    TaskEvent,
    TaskStatus,
)
from auraeve.subagents.data.repositories import SubagentDB
from auraeve.session.manager import SessionManager
from auraeve.webui.chat_console_service import ChatConsoleService
from auraeve.webui.chat_service import ChatService, RunState


class _FakeBus:
    async def publish_inbound(self, msg) -> None:  # pragma: no cover - 测试中不需要动作
        return None


def test_chat_console_snapshot_filters_session_tasks_and_extracts_tools(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    db = SubagentDB(tmp_path / "subagent.db")
    sm = SessionManager(sessions_dir)
    session_key = "webui:test-user"

    session = sm.get_or_create(session_key)
    session.add_message("user", "帮我分析最近的任务状态")
    session.add_message(
        "assistant",
        "",
        tool_calls=[
            {
                "id": "call_sub_1",
                "type": "function",
                "function": {"name": "subagent", "arguments": "{\"goal\":\"分析任务\"}"},
            }
        ],
    )
    session.add_message("tool", "{\"ok\": true}", tool_call_id="call_sub_1", name="subagent")
    session.add_message("assistant", "已派出一个子体并等待结果。")
    sm.save(session)

    task = Task(
        task_id="task_1",
        goal="分析任务",
        assigned_node_id="local",
        priority=8,
        status=TaskStatus.RUNNING,
        budget=TaskBudget(),
        trace_id="trace-1",
        origin_channel="webui",
        origin_chat_id=session_key,
    )
    db.save_task(task)
    db.append_event(
        TaskEvent(
            task_id="task_1",
            seq=1,
            event_type="state_change",
            payload={"from": "queued", "to": "running", "reason": "local_start"},
            trace_id="trace-1",
        )
    )
    db.append_event(
        TaskEvent(
            task_id="task_1",
            seq=2,
            event_type="span",
            payload={"operation": "progress", "message": "正在拆解执行步骤", "status": "ok"},
            trace_id="trace-1",
        )
    )
    db.save_task(
        Task(
            task_id="task_2",
            goal="不相关任务",
            assigned_node_id="node-x",
            priority=5,
            status=TaskStatus.COMPLETED,
            budget=TaskBudget(),
            trace_id="trace-2",
            origin_channel="webui",
            origin_chat_id="webui:other-user",
        )
    )
    db.save_approval(
        Approval(
            approval_id="apv-1",
            task_id="task_1",
            action_desc="批准执行外部命令",
            risk_level=RiskLevel.HIGH,
            status=ApprovalStatus.PENDING,
        )
    )
    db.upsert_node(NodeSession(node_id="local", display_name="本地节点", platform="windows", is_online=True))
    db.upsert_node(NodeSession(node_id="node-x", display_name="远程节点", platform="linux", is_online=False))

    chat = ChatService(sm, _FakeBus())
    chat._runs["run-1"] = RunState(run_id="run-1", session_key=session_key, idempotency_key="ik-1", done=False)

    service = ChatConsoleService(chat_service=chat, db=db)

    snapshot = service.get_snapshot(session_key)

    assert snapshot["run"]["status"] == "running"
    assert snapshot["run"]["runId"] == "run-1"
    assert len(snapshot["tasks"]) == 1
    assert snapshot["tasks"][0]["taskId"] == "task_1"
    assert len(snapshot["approvals"]) == 1
    assert snapshot["approvals"][0]["approvalId"] == "apv-1"
    assert snapshot["toolCalls"][0]["toolName"] == "subagent"
    assert snapshot["toolCalls"][0]["status"] == "completed"
    assert snapshot["toolCalls"][0]["resultPreview"] == "{\"ok\": true}"
    assert snapshot["timeline"][0]["taskId"] == "task_1"
    assert snapshot["summary"]["runningTasks"] == 1
