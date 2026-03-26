from auraeve.transports.acp.bridge import ACPBridge
from auraeve.transports.acp.mapper import build_dev_session_key


def test_build_dev_session_key() -> None:
    assert build_dev_session_key("main", "ws1", "thread-a") == "dev:main:ws1:thread-a"


def test_build_dev_session_key_escapes_reserved_characters() -> None:
    assert build_dev_session_key("ma:in", "ws:1", "th:read") == "dev:ma\\:in:ws\\:1:th\\:read"


def test_acp_bridge_reuses_session_by_thread_identity() -> None:
    bridge = ACPBridge()

    first = bridge.get_or_create_session("main", "ws1", "thread-a")
    second = bridge.get_or_create_session("main", "ws1", "thread-a")

    assert first.session_id.startswith("dev-session:")
    assert first.session_key == "dev:main:ws1:thread-a"
    assert first.session_type == "dev_acp"
    assert first.runtime_type == "acp"
    assert first is second
