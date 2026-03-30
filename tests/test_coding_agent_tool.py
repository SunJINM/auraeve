from pathlib import Path

import pytest

from auraeve.agent.tools.coding_agent import CodingAgentTool


class FakeService:
    def __init__(self):
        self.run_calls = []
        self.status_calls = []
        self.cancel_calls = []
        self.close_calls = []

    async def run(self, **kwargs):
        self.run_calls.append(kwargs)
        return type(
            "Result",
            (),
            {
                "status": "ok",
                "target": kwargs["requested_target"],
                "session_id": "sess-1",
                "summary": "执行完成",
                "final_text": "补丁已生成",
                "error": None,
                "suggested_next_action": None,
            },
        )()

    async def status(self, session_id: str, *, origin_session_key: str):
        self.status_calls.append((session_id, origin_session_key))
        return type(
            "Handle",
            (),
            {
                "session_id": session_id,
                "status": "idle",
                "target": "codex",
                "cwd": "D:/repo",
                "mode": "session",
            },
        )()

    async def cancel(self, session_id: str, *, origin_session_key: str):
        self.cancel_calls.append((session_id, origin_session_key))
        return type("Handle", (), {"session_id": session_id, "status": "aborted"})()

    async def close(self, session_id: str, *, origin_session_key: str):
        self.close_calls.append((session_id, origin_session_key))
        return type("Handle", (), {"session_id": session_id, "status": "closed"})()


@pytest.mark.asyncio
async def test_tool_run_returns_summary(tmp_path: Path):
    service = FakeService()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = CodingAgentTool(
        service=service,
        origin_session_key_getter=lambda: "terminal:chat",
    )
    text = await tool.execute(
        action="run",
        task="修复测试",
        target="codex",
        mode="oneshot",
        cwd=str(workspace),
        timeout_s=60,
        expected_output="patch",
        context_mode="summary",
    )
    assert "执行完成" in text
    assert "补丁已生成" in text
    assert service.run_calls[0]["origin_session_key"] == "terminal:chat"


@pytest.mark.asyncio
async def test_tool_run_rejects_cwd_outside_allowed_dir(tmp_path: Path):
    service = FakeService()
    allowed_dir = tmp_path / "workspace"
    allowed_dir.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    tool = CodingAgentTool(
        service=service,
        origin_session_key_getter=lambda: "terminal:chat",
        allowed_dir=allowed_dir,
    )

    text = await tool.execute(
        action="run",
        task="修复测试",
        target="codex",
        mode="oneshot",
        cwd=str(outside_dir),
        timeout_s=60,
        expected_output="patch",
        context_mode="summary",
    )

    assert "escapes allowed dir" in text
    assert service.run_calls == []


def test_tool_validate_rejects_missing_task():
    tool = CodingAgentTool(
        service=FakeService(),
        origin_session_key_getter=lambda: "terminal:chat",
    )
    errors = tool.validate_params({"action": "run", "target": "auto"})
    assert errors


@pytest.mark.asyncio
async def test_tool_status_uses_origin_session_key():
    service = FakeService()
    tool = CodingAgentTool(
        service=service,
        origin_session_key_getter=lambda: "terminal:chat",
    )

    text = await tool.execute(action="status", session_id="sess-1")

    assert "status: idle" in text
    assert service.status_calls == [("sess-1", "terminal:chat")]


@pytest.mark.asyncio
async def test_tool_run_with_real_service_stack(tmp_path):
    from auraeve.external_agents.adapters.acpx_adapter import AcpxAdapter
    from auraeve.external_agents.registry import build_default_external_agent_registry
    from auraeve.external_agents.service import ExternalAgentService
    from auraeve.external_agents.store import ExternalAgentSessionStore

    class FakeRunner:
        async def run(self, argv, cwd, timeout_s):
            return {"stdout": "done", "stderr": "", "returncode": 0}

    service = ExternalAgentService(
        runtime=AcpxAdapter(command="acpx", process_runner=FakeRunner()),
        registry=build_default_external_agent_registry(),
        store=ExternalAgentSessionStore(tmp_path / "sessions.json"),
    )
    tool = CodingAgentTool(
        service=service,
        origin_session_key_getter=lambda: "terminal:chat",
    )
    text = await tool.execute(
        action="run",
        task="修复单元测试",
        target="codex",
        mode="oneshot",
        cwd=str(tmp_path),
        timeout_s=30,
        expected_output="patch",
        context_mode="summary",
    )
    assert "status: ok" in text
    assert "final_text: done" in text
