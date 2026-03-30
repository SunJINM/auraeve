from pathlib import Path
import asyncio

from auraeve.external_agents.models import ExternalRunResult, ExternalSessionHandle
from auraeve.external_agents.registry import build_default_external_agent_registry
from auraeve.external_agents.service import ExternalAgentService
from auraeve.external_agents.store import ExternalAgentSessionStore


class FakeRuntime:
    def __init__(self):
        self.ensure_calls = []
        self.run_calls = []

    async def ensure_session(self, **kwargs):
        self.ensure_calls.append(kwargs)
        return ExternalSessionHandle(
            session_id=kwargs["session_id"],
            target=kwargs["target"],
            mode=kwargs["mode"],
            cwd=kwargs["cwd"],
            status="idle",
            created_at=1.0,
            updated_at=1.0,
            origin_session_key=kwargs["origin_session_key"],
            execution_target=kwargs["execution_target"],
        )

    async def run_turn(self, request, handle):
        self.run_calls.append((request, handle))
        return ExternalRunResult(
            status="ok",
            target=handle.target,
            session_id=handle.session_id,
            final_text="完成",
            summary="完成",
            artifacts=[],
            raw_output_ref=None,
            error=None,
            usage={},
            suggested_next_action=None,
        )

    async def cancel(self, handle):
        handle.status = "aborted"
        return handle

    async def close(self, handle):
        handle.status = "closed"
        return handle

    async def get_status(self, handle):
        return handle


def test_pick_target_prefers_claude_for_review(tmp_path: Path):
    service = ExternalAgentService(
        runtime=FakeRuntime(),
        registry=build_default_external_agent_registry(),
        store=ExternalAgentSessionStore(tmp_path / "sessions.json"),
    )
    assert service.pick_target(task="请帮我 review 这段代码", requested_target="auto") == "claude"


def test_pick_target_prefers_codex_for_fix(tmp_path: Path):
    service = ExternalAgentService(
        runtime=FakeRuntime(),
        registry=build_default_external_agent_registry(),
        store=ExternalAgentSessionStore(tmp_path / "sessions.json"),
    )
    assert service.pick_target(task="修复测试并修改文件", requested_target="auto") == "codex"


def test_reuse_session_when_mode_is_session(tmp_path: Path):
    service = ExternalAgentService(
        runtime=FakeRuntime(),
        registry=build_default_external_agent_registry(),
        store=ExternalAgentSessionStore(tmp_path / "sessions.json"),
    )
    existing = ExternalSessionHandle(
        session_id="sess-1",
        target="codex",
        mode="session",
        cwd="D:/repo",
        status="idle",
        created_at=1.0,
        updated_at=1.0,
        origin_session_key="terminal:chat",
        execution_target="local",
    )
    service._store.save(existing)
    reused = service.resolve_reusable_session(
        origin_session_key="terminal:chat",
        target="codex",
        cwd="D:/repo",
        mode="session",
    )
    assert reused is not None
    assert reused.session_id == "sess-1"


def test_service_status_returns_none_for_missing_session(tmp_path: Path):
    service = ExternalAgentService(
        runtime=FakeRuntime(),
        registry=build_default_external_agent_registry(),
        store=ExternalAgentSessionStore(tmp_path / "sessions.json"),
    )
    assert asyncio.run(service.status("missing")) is None
