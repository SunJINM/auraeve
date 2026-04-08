import importlib
import inspect
import subprocess

from auraeve.agent_runtime.kernel import RuntimeKernel
from auraeve.subagents.executor import SubagentExecutor


def test_kernel_has_no_legacy_resume_or_system_message_paths() -> None:
    assert not hasattr(RuntimeKernel, "run")
    assert not hasattr(RuntimeKernel, "_process_system_message")
    assert not hasattr(RuntimeKernel, "_resume_with_subagent_result")


def test_subagent_executor_signature_has_no_kernel_resume_callback() -> None:
    signature = inspect.signature(SubagentExecutor)

    assert "kernel_resume_callback" not in signature.parameters


def test_subagents_package_does_not_export_notification_queue() -> None:
    subagents = importlib.import_module("auraeve.subagents")
    notification = importlib.import_module("auraeve.subagents.notification")

    assert "NotificationQueue" not in getattr(subagents, "__all__", [])
    assert not hasattr(notification, "NotificationQueue")


def test_no_governor_reference_call_sites_left() -> None:
    result = subprocess.run(
        ["rg", "-n", "_governor\\b", "auraeve", "main.py"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
