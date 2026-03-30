from __future__ import annotations

from typing import Any, Callable

from auraeve.agent.tools.base import Tool


class CodingAgentTool(Tool):
    def __init__(self, *, service, origin_session_key_getter: Callable[[], str]) -> None:
        self._service = service
        self._origin_session_key_getter = origin_session_key_getter

    @property
    def name(self) -> str:
        return "coding_agent"

    @property
    def description(self) -> str:
        return "调用外部编码智能体能力，支持 run/status/cancel/close。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["run", "status", "cancel", "close"],
                },
                "task": {"type": "string"},
                "target": {"type": "string", "enum": ["auto", "claude", "codex"]},
                "mode": {"type": "string", "enum": ["oneshot", "session"]},
                "cwd": {"type": "string"},
                "session_id": {"type": "string"},
                "label": {"type": "string"},
                "timeout_s": {"type": "integer", "minimum": 1},
                "expected_output": {
                    "type": "string",
                    "enum": ["generic", "summary", "patch", "review"],
                },
                "context_mode": {
                    "type": "string",
                    "enum": ["summary", "full_prompt"],
                },
            },
            "required": ["action"],
        }

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = super().validate_params(params)
        action = params.get("action")
        if action == "run":
            for key in (
                "task",
                "target",
                "mode",
                "cwd",
                "timeout_s",
                "expected_output",
                "context_mode",
            ):
                if key not in params:
                    errors.append(f"缺少必填字段：{key}")
        if action in {"status", "cancel", "close"} and "session_id" not in params:
            errors.append("缺少必填字段：session_id")
        return errors

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]
        if action == "run":
            result = await self._service.run(
                task=kwargs["task"],
                requested_target=kwargs["target"],
                cwd=kwargs["cwd"],
                mode=kwargs["mode"],
                label=kwargs.get("label"),
                timeout_s=kwargs["timeout_s"],
                context_mode=kwargs["context_mode"],
                expected_output=kwargs["expected_output"],
                origin_session_key=self._origin_session_key_getter(),
            )
            return (
                f"status: {result.status}\n"
                f"target: {result.target}\n"
                f"session_id: {result.session_id}\n"
                f"summary: {result.summary}\n"
                f"final_text: {result.final_text}"
            )
        if action == "status":
            handle = await self._service.status(kwargs["session_id"])
            return (
                "session not found"
                if handle is None
                else (
                    f"session_id: {handle.session_id}\n"
                    f"status: {handle.status}\n"
                    f"target: {handle.target}\n"
                    f"cwd: {handle.cwd}\n"
                    f"mode: {handle.mode}"
                )
            )
        if action == "cancel":
            handle = await self._service.cancel(kwargs["session_id"])
            return (
                "session not found"
                if handle is None
                else f"session_id: {handle.session_id}\nstatus: {handle.status}"
            )
        handle = await self._service.close(kwargs["session_id"])
        return (
            "session not found"
            if handle is None
            else f"session_id: {handle.session_id}\nstatus: {handle.status}"
        )
