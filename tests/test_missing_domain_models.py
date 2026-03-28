def test_patchset_model_fields() -> None:
    from auraeve.domain.patches.models import PatchSet
    item = PatchSet(
        patch_id="p1",
        session_id="s1",
        run_id="r1",
        files=["src/foo.py"],
        status="proposed",
    )
    assert item.patch_id == "p1"
    assert item.files == ["src/foo.py"]
    assert item.applied_at is None


def test_execution_record_model_fields() -> None:
    from auraeve.domain.executions.models import ExecutionRecord
    item = ExecutionRecord(
        execution_id="e1",
        session_id="s1",
        run_id="r1",
        command="pytest",
        cwd="/repo",
        exit_code=0,
    )
    assert item.exit_code == 0
    assert item.stdout_summary == ""
    assert item.stderr_summary == ""


def test_approval_request_model_fields() -> None:
    from auraeve.domain.approvals.models import ApprovalRequest
    item = ApprovalRequest(
        approval_id="a1",
        session_id="s1",
        run_id="r1",
        action_type="shell_exec",
        risk_level="high",
        status="pending",
    )
    assert item.status == "pending"
    assert item.resolved_by is None
