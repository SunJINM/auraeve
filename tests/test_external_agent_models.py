from auraeve.external_agents.models import (
    ExternalRunRequest,
    ExternalRunResult,
    ExternalSessionHandle,
)


def test_external_session_handle_defaults():
    handle = ExternalSessionHandle(
        session_id="sess-1",
        target="codex",
        mode="oneshot",
        cwd="D:/repo",
        status="idle",
        created_at=1.0,
        updated_at=1.0,
        origin_session_key="terminal:chat",
        execution_target="local",
    )
    assert handle.backend_session_ref is None
    assert handle.node_id is None
    assert handle.last_error is None


def test_external_run_request_keeps_expected_output():
    request = ExternalRunRequest(
        task="修复测试",
        target="codex",
        cwd="D:/repo",
        mode="oneshot",
        label="fix-tests",
        timeout_s=120,
        context_mode="summary",
        expected_output="patch",
        session_id=None,
        execution_target="local",
    )
    assert request.expected_output == "patch"


def test_external_run_result_retryable_flag():
    result = ExternalRunResult(
        status="error",
        target="claude",
        session_id="sess-2",
        final_text="",
        summary="权限失败",
        artifacts=[],
        raw_output_ref=None,
        error="permission denied",
        usage={},
        suggested_next_action="adjust_permissions",
        error_type="permission_denied_noninteractive",
        retryable=False,
        session_survived=False,
    )
    assert result.retryable is False
    assert result.error_type == "permission_denied_noninteractive"
