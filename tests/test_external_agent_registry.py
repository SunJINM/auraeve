from auraeve.external_agents.registry import build_default_external_agent_registry


def test_registry_contains_claude_and_codex():
    registry = build_default_external_agent_registry()
    assert registry.has("claude")
    assert registry.has("codex")


def test_registry_get_auto_candidates():
    registry = build_default_external_agent_registry()
    ids = {target.id for target in registry.list_targets()}
    assert "claude" in ids
    assert "codex" in ids
