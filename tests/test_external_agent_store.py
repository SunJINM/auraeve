from pathlib import Path

from auraeve.external_agents.models import ExternalSessionHandle
from auraeve.external_agents.store import ExternalAgentSessionStore


def test_store_save_and_get(tmp_path: Path):
    store = ExternalAgentSessionStore(tmp_path / "external_sessions.json")
    handle = ExternalSessionHandle(
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
    store.save(handle)
    loaded = store.get("sess-1")
    assert loaded is not None
    assert loaded.target == "codex"
    assert loaded.mode == "session"


def test_store_find_reusable_session(tmp_path: Path):
    store = ExternalAgentSessionStore(tmp_path / "external_sessions.json")
    handle = ExternalSessionHandle(
        session_id="sess-2",
        target="claude",
        mode="session",
        cwd="D:/repo",
        status="idle",
        created_at=2.0,
        updated_at=2.0,
        origin_session_key="terminal:chat",
        execution_target="local",
    )
    store.save(handle)
    loaded = store.find_reusable(
        origin_session_key="terminal:chat",
        target="claude",
        cwd="D:/repo",
    )
    assert loaded is not None
    assert loaded.session_id == "sess-2"
