"""协议编解码。"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any


def encode(msg: Any) -> str:
    """将协议消息编码为 JSON 字符串。"""
    if hasattr(msg, "__dataclass_fields__"):
        d = asdict(msg)
    elif isinstance(msg, dict):
        d = msg
    else:
        raise TypeError(f"无法编码: {type(msg)}")
    return json.dumps(d, ensure_ascii=False)


def decode(raw: str | bytes) -> dict[str, Any]:
    """将 JSON 字符串解码为字典。"""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)
