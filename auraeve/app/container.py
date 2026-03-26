"""Application container for composed services and runtime registries."""

from auraeve.app.runtime_registry import RuntimeRegistry


class AppContainer:
    """Lightweight application container scaffold."""

    def __init__(self) -> None:
        self.runtime_registry = RuntimeRegistry()
