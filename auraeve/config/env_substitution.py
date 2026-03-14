from __future__ import annotations

import os
import re
from typing import Any


ENV_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
ENV_ESCAPED_PATTERN = re.compile(r"\$\$\{([A-Z_][A-Z0-9_]*)\}")


def substitute_env(value: Any, warnings: list[dict[str, str]], path: str = "") -> Any:
    if isinstance(value, dict):
        return {
            key: substitute_env(child, warnings, f"{path}.{key}" if path else key)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [substitute_env(item, warnings, f"{path}[{idx}]") for idx, item in enumerate(value)]
    if not isinstance(value, str):
        return value

    escaped = ENV_ESCAPED_PATTERN.sub(lambda m: f"__ESCAPED_ENV__{m.group(1)}__", value)

    def _replace(match: re.Match[str]) -> str:
        env_key = match.group(1)
        env_val = os.environ.get(env_key, "")
        if env_val == "":
            warnings.append(
                {
                    "path": path or "<root>",
                    "message": f'missing env var "{env_key}"',
                }
            )
            return match.group(0)
        return env_val

    resolved = ENV_PATTERN.sub(_replace, escaped)
    return re.sub(r"__ESCAPED_ENV__([A-Z_][A-Z0-9_]*)__", r"${\1}", resolved)
