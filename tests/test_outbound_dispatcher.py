import importlib

from auraeve.bus.queue import OutboundDispatcher


def test_outbound_dispatcher_is_exported_from_bus_queue() -> None:
    module = importlib.import_module("auraeve.bus.queue")

    assert hasattr(module, "OutboundDispatcher")
    assert not hasattr(module, "MessageBus")
    assert OutboundDispatcher is module.OutboundDispatcher
