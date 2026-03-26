from auraeve.domain.sessions.repository import SessionRepository
from auraeve.domain.sessions.models import SessionRecord


def test_session_record_defaults() -> None:
    item = SessionRecord(
        session_id="s1",
        session_key="dev:main:ws1:t1",
        session_type="dev_acp",
        runtime_type="acp",
        agent_id="main",
        workspace_id="ws1",
        thread_id="t1",
        state="idle",
    )

    assert item.session_key == "dev:main:ws1:t1"
    assert item.metadata == {}


def test_session_repository_save_get_list_and_get_by_key() -> None:
    repo = SessionRepository()
    first = SessionRecord(
        session_id="s1",
        session_key="dev:main:ws1:t1",
        session_type="dev_acp",
        runtime_type="acp",
        agent_id="main",
        workspace_id="ws1",
        thread_id="t1",
        state="idle",
    )
    second = SessionRecord(
        session_id="s2",
        session_key="dev:main:ws2:t2",
        session_type="dev_acp",
        runtime_type="acp",
        agent_id="main",
        workspace_id="ws2",
        thread_id="t2",
        state="running",
    )

    repo.save(first)
    repo.save(second)

    assert repo.get("s1") is first
    assert repo.get_by_key("dev:main:ws2:t2") is second
    assert repo.list() == [first, second]
