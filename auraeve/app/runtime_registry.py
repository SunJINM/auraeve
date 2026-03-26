"""Registry for runtime implementations."""


class RuntimeRegistry:
    def __init__(self) -> None:
        self._items: dict[str, object] = {}

    def register(self, name: str, runtime: object) -> None:
        if name in self._items:
            raise ValueError(f"runtime already registered: {name}")
        self._items[name] = runtime

    def get(self, name: str) -> object | None:
        return self._items.get(name)

