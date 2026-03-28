from pathlib import Path

from auraeve.domain.sessions.models import SessionRecord
from auraeve.domain.sessions.repository import SessionRepository


def _make_session(session_id: str = "s1") -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        session_key=f"dev:agent:{session_id}:t1",
        session_type="dev_acp",
        runtime_type="acp",
        agent_id="agent",
        workspace_id=session_id,
        thread_id="t1",
        state="idle",
    )


def test_session_repository_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "sessions.jsonl"

    repo1 = SessionRepository(path)
    repo1.save(_make_session("s1"))

    repo2 = SessionRepository(path)
    assert repo2.get("s1") is not None
    assert repo2.get("s1").session_key == "dev:agent:s1:t1"


def test_session_repository_get_by_key_after_reload(tmp_path: Path) -> None:
    path = tmp_path / "sessions.jsonl"

    repo1 = SessionRepository(path)
    repo1.save(_make_session("s2"))

    repo2 = SessionRepository(path)
    result = repo2.get_by_key("dev:agent:s2:t1")
    assert result is not None
    assert result.session_id == "s2"


def test_session_repository_in_memory_still_works() -> None:
    repo = SessionRepository()
    repo.save(_make_session("s3"))
    assert repo.get("s3") is not None
