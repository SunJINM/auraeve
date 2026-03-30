from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from auraeve.agent.tools.base import Tool


class CodingAgentTool(Tool):
    def __init__(
        self,
        *,
        service,
        origin_session_key_getter: Callable[[], str],
        allowed_dir: Path | None = None,
    ) -> None:
        self._service = service
        self._origin_session_key_getter = origin_session_key_getter
        self._allowed_dir = allowed_dir.resolve() if allowed_dir is not None else None

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

    def _resolve_cwd(self, cwd: str) -> str:
        resolved = Path(cwd).expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"working directory does not exist: {cwd}")
        if not resolved.is_dir():
            raise NotADirectoryError(f"working directory is not a directory: {cwd}")
        if self._allowed_dir is not None and resolved != self._allowed_dir and self._allowed_dir not in resolved.parents:
            raise PermissionError(
                f"working directory {resolved} escapes allowed dir {self._allowed_dir}"
            )
        return str(resolved)

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]
        origin_session_key = self._origin_session_key_getter()
        if action == "run":
            try:
                cwd = self._resolve_cwd(kwargs["cwd"])
            except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
                return f"Error: {exc}"
            result = await self._service.run(
                task=kwargs["task"],
                requested_target=kwargs["target"],
                cwd=cwd,
                mode=kwargs["mode"],
                label=kwargs.get("label"),
                timeout_s=kwargs["timeout_s"],
                context_mode=kwargs["context_mode"],
                expected_output=kwargs["expected_output"],
                origin_session_key=origin_session_key,
            )
            return (
                f"status: {result.status}\n"
                f"target: {result.target}\n"
                f"session_id: {result.session_id}\n"
                f"summary: {result.summary}\n"
                f"final_text: {result.final_text}"
            )
        if action == "status":
            handle = await self._service.status(
                kwargs["session_id"],
                origin_session_key=origin_session_key,
            )
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
            handle = await self._service.cancel(
                kwargs["session_id"],
                origin_session_key=origin_session_key,
            )
            return (
                "session not found"
                if handle is None
                else f"session_id: {handle.session_id}\nstatus: {handle.status}"
            )
        handle = await self._service.close(
            kwargs["session_id"],
            origin_session_key=origin_session_key,
        )
        return (
            "session not found"
            if handle is None
            else f"session_id: {handle.session_id}\nstatus: {handle.status}"
        )
