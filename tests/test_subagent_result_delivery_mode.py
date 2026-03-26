from auraeve.subagents.control_plane.orchestrator import _resolve_delivery_mode


def test_dev_acp_sessions_use_transcript_delivery_mode() -> None:
    value = _resolve_delivery_mode({"session_type": "dev_acp"})

    assert value == "dev_transcript"


def test_other_sessions_stay_on_mother_chat_delivery_mode() -> None:
    assert _resolve_delivery_mode(None) == "mother_chat"
