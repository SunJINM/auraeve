import pytest

from auraeve.external_agents.adapters.acpx_adapter import AcpxAdapter
from auraeve.external_agents.models import ExternalRunRequest


class FakeProcessRunner:
    def __init__(self, *, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.calls = []

    async def run(self, argv, cwd, timeout_s):
        self.calls.append((argv, cwd, timeout_s))
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
        }


@pytest.mark.asyncio
async def test_adapter_run_turn_returns_success_result():
    runner = FakeProcessRunner(stdout="done", returncode=0)
    adapter = AcpxAdapter(command="acpx", process_runner=runner)
    handle = await adapter.ensure_session(
        target="codex",
        session_id="sess-1",
        cwd="D:/repo",
        mode="oneshot",
        origin_session_key="terminal:chat",
        execution_target="local",
    )
    request = ExternalRunRequest(
        task="修复测试",
        target="codex",
        cwd="D:/repo",
        mode="oneshot",
        label=None,
        timeout_s=60,
        context_mode="summary",
        expected_output="patch",
        session_id="sess-1",
        execution_target="local",
    )
    result = await adapter.run_turn(request, handle)
    assert result.status == "ok"
    assert result.final_text == "done"


@pytest.mark.asyncio
async def test_adapter_maps_permission_error():
    runner = FakeProcessRunner(stderr="permission denied", returncode=5)
    adapter = AcpxAdapter(command="acpx", process_runner=runner)
    handle = await adapter.ensure_session(
        target="claude",
        session_id="sess-2",
        cwd="D:/repo",
        mode="session",
        origin_session_key="terminal:chat",
        execution_target="local",
    )
    request = ExternalRunRequest(
        task="执行任务",
        target="claude",
        cwd="D:/repo",
        mode="session",
        label=None,
        timeout_s=60,
        context_mode="summary",
        expected_output="generic",
        session_id="sess-2",
        execution_target="local",
    )
    result = await adapter.run_turn(request, handle)
    assert result.status == "error"
    assert result.error_type == "permission_denied_noninteractive"
    assert result.retryable is False


@pytest.mark.asyncio
async def test_adapter_maps_timeout_error():
    runner = FakeProcessRunner(stderr="command timed out after 60s", returncode=124)
    adapter = AcpxAdapter(command="acpx", process_runner=runner)
    handle = await adapter.ensure_session(
        target="codex",
        session_id="sess-3",
        cwd="D:/repo",
        mode="oneshot",
        origin_session_key="terminal:chat",
        execution_target="local",
    )
    request = ExternalRunRequest(
        task="执行任务",
        target="codex",
        cwd="D:/repo",
        mode="oneshot",
        label=None,
        timeout_s=60,
        context_mode="summary",
        expected_output="generic",
        session_id="sess-3",
        execution_target="local",
    )

    result = await adapter.run_turn(request, handle)

    assert result.status == "error"
    assert result.error_type == "timeout"
    assert result.retryable is False


@pytest.mark.asyncio
async def test_adapter_process_error_is_retryable():
    runner = FakeProcessRunner(stderr="temporary backend error", returncode=2)
    adapter = AcpxAdapter(command="acpx", process_runner=runner)
    handle = await adapter.ensure_session(
        target="codex",
        session_id="sess-3",
        cwd="D:/repo",
        mode="oneshot",
        origin_session_key="terminal:chat",
        execution_target="local",
    )
    request = ExternalRunRequest(
        task="执行任务",
        target="codex",
        cwd="D:/repo",
        mode="oneshot",
        label=None,
        timeout_s=60,
        context_mode="summary",
        expected_output="generic",
        session_id="sess-3",
        execution_target="local",
    )
    result = await adapter.run_turn(request, handle)
    assert result.retryable is True
    assert result.error_type == "process_error"
