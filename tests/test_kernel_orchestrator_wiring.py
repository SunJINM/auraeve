from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.agent_runtime.kernel import RuntimeKernel
from auraeve.agent_runtime.runtime_scheduler import RuntimeScheduler


def test_kernel_initialize_command_runtime_exposes_queue_and_scheduler() -> None:
    kernel = object.__new__(RuntimeKernel)

    RuntimeKernel._initialize_command_runtime(kernel)

    assert isinstance(kernel.command_queue, RuntimeCommandQueue)
    assert isinstance(kernel.scheduler, RuntimeScheduler)


def test_kernel_initialize_command_runtime_uses_execute_command_callback() -> None:
    kernel = object.__new__(RuntimeKernel)

    RuntimeKernel._initialize_command_runtime(kernel)

    assert kernel.scheduler._run_command == kernel.execute_command
