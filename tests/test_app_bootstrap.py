from auraeve.app import bootstrap
from auraeve.app.bootstrap import create_application
from auraeve.app.container import AppContainer


def test_create_application_returns_app_container() -> None:
    app = create_application()

    assert isinstance(app, AppContainer)
    assert app.runtime_registry is not None
    assert app.dev_session_service is not None
    assert app.runtime_registry.get("acp") is not None


def test_run_application_creates_and_enters_runtime_with_container(monkeypatch) -> None:
    sentinel = AppContainer()
    calls: list[tuple[AppContainer, bool]] = []

    async def fake_runtime(application: AppContainer, terminal_mode: bool) -> None:
        calls.append((application, terminal_mode))

    monkeypatch.setattr(bootstrap, "create_application", lambda: sentinel)
    monkeypatch.setattr(bootstrap, "_run_runtime", fake_runtime)

    app = bootstrap.run_application(terminal_mode=True)

    assert app is sentinel
    assert calls == [(sentinel, True)]
