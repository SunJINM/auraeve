from __future__ import annotations

from .command_types import QueuedCommand


def project_command_to_messages(command: QueuedCommand) -> list[dict]:
    if command.mode == "prompt":
        return [{"role": "user", "content": str(command.payload.get("content", ""))}]

    if command.mode == "task-notification":
        payload = command.payload
        text = (
            "A background agent completed a task:\n"
            f"- task_id: {payload.get('task_id', '')}\n"
            f"- agent_type: {payload.get('agent_type', '')}\n"
            f"- goal: {payload.get('goal', '')}\n"
            f"- status: {payload.get('status', '')}\n"
            f"- result: {payload.get('result', '')}"
        )
        return [{"role": "user", "content": text}]

    if command.mode in {"cron", "heartbeat"}:
        return [{"role": "user", "content": str(command.payload.get("content", ""))}]

    raise ValueError(f"Unsupported command mode: {command.mode}")
