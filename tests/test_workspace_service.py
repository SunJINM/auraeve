from pathlib import Path

from auraeve.domain.sessions.models import SessionRecord
from auraeve.services.session_service import SessionService
from auraeve.services.workspace_service import WorkspaceService


def test_workspace_service_creates_workspace_record(tmp_path: Path) -> None:
    service = WorkspaceService()

    item = service.build_workspace("ws1", tmp_path)

    assert item.workspace_id == "ws1"
    assert item.path == str(tmp_path)
    assert item.repo_root == str(tmp_path)
    assert item.status == "ready"
    assert item.metadata == {}


def test_workspace_service_normalizes_paths(tmp_path: Path) -> None:
    service = WorkspaceService()
    raw_path = tmp_path / ".." / tmp_path.name

    item = service.build_workspace("ws1", raw_path)

    assert item.path == str(tmp_path.resolve(strict=False))
    assert item.repo_root == str(tmp_path.resolve(strict=False))


def test_session_service_roundtrip() -> None:
    service = SessionService()
    session = SessionRecord(
        session_id="s1",
        session_key="dev:main:ws1:t1",
        session_type="dev_acp",
        runtime_type="acp",
        agent_id="main",
        workspace_id="ws1",
        thread_id="t1",
        state="idle",
    )

    created = service.create_session(session)

    assert created is session
    assert service.get_session("s1") is session
    assert service.get_session_by_key("dev:main:ws1:t1") is session
    assert service.list_sessions() == [session]
