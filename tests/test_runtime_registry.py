from pathlib import Path

from auraeve.app.runtime_registry import RuntimeRegistry


class _Runtime:
    def __init__(self, name: str) -> None:
        self.name = name


def test_runtime_registry_register_and_resolve() -> None:
    registry = RuntimeRegistry()
    runtime = _Runtime("acp")

    registry.register("acp", runtime)

    assert registry.get("acp") is runtime


def test_runtime_registry_rejects_duplicate_names() -> None:
    registry = RuntimeRegistry()
    registry.register("acp", object())

    try:
        registry.register("acp", object())
    except ValueError as exc:
        assert "acp" in str(exc)
    else:
        raise AssertionError("expected duplicate runtime registration to fail")
