import pytest

from auraeve.external_agents.models import ExternalAgentTarget
from auraeve.external_agents.registry import (
    ExternalAgentRegistry,
    build_default_external_agent_registry,
)


def test_registry_contains_claude_and_codex():
    registry = build_default_external_agent_registry()
    assert registry.has("claude")
    assert registry.has("codex")


def test_registry_get_auto_candidates():
    registry = build_default_external_agent_registry()
    ids = {target.id for target in registry.list_targets()}
    assert "claude" in ids
    assert "codex" in ids


def test_registry_get_returns_none_for_unknown_target():
    registry = build_default_external_agent_registry()
    assert registry.get("unknown") is None


def test_registry_rejects_duplicate_registration():
    registry = ExternalAgentRegistry()
    registry.register(ExternalAgentTarget(id="codex"))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(ExternalAgentTarget(id="codex"))


def test_registry_register_then_get_returns_same_target():
    registry = ExternalAgentRegistry()
    target = ExternalAgentTarget(id="claude", supports_options=["model"])

    registry.register(target)

    assert registry.get("claude") is target
