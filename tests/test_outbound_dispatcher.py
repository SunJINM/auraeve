import importlib
import subprocess

from auraeve.bus.queue import OutboundDispatcher


def test_outbound_dispatcher_is_exported_from_bus_queue() -> None:
    module = importlib.import_module("auraeve.bus.queue")

    assert hasattr(module, "OutboundDispatcher")
    assert not hasattr(module, "MessageBus")
    assert OutboundDispatcher is module.OutboundDispatcher


def test_main_no_longer_contains_embedded_runtime_apply_handler() -> None:
    result = subprocess.run(
        ["rg", "-n", "async def _on_runtime_apply", "main.py"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
