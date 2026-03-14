from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MAX_INCLUDE_DEPTH = 10
MAX_INCLUDE_FILE_BYTES = 2 * 1024 * 1024
INCLUDE_KEY = "$include"


def _strip_json_comments(raw: str) -> str:
    out: list[str] = []
    i = 0
    in_string = False
    in_line_comment = False
    in_block_comment = False
    while i < len(raw):
        ch = raw[i]
        nxt = raw[i + 1] if i + 1 < len(raw) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_string:
            out.append(ch)
            if ch == "\\":
                if i + 1 < len(raw):
                    out.append(raw[i + 1])
                    i += 2
                    continue
            elif ch == "\"":
                in_string = False
            i += 1
            continue
        if ch == "\"":
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _parse_json(raw: str) -> dict[str, Any]:
    payload = json.loads(_strip_json_comments(raw))
    if not isinstance(payload, dict):
        raise ValueError("config root must be an object")
    return payload


def _ensure_include_inside(root_dir: Path, candidate: Path) -> Path:
    real_root = root_dir.resolve()
    real_candidate = candidate.resolve()
    if real_root == real_candidate or real_root in real_candidate.parents:
        return real_candidate
    raise ValueError(f"include path escapes config root: {candidate}")


def _deep_merge(a: Any, b: Any) -> Any:
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for key, value in b.items():
            if key in out:
                out[key] = _deep_merge(out[key], value)
            else:
                out[key] = value
        return out
    if isinstance(a, list) and isinstance(b, list):
        return [*a, *b]
    return b


def resolve_includes(obj: Any, base_path: Path, root_dir: Path, depth: int = 0) -> Any:
    if depth > MAX_INCLUDE_DEPTH:
        raise ValueError(f"maximum include depth exceeded: {MAX_INCLUDE_DEPTH}")
    if isinstance(obj, list):
        return [resolve_includes(item, base_path, root_dir, depth) for item in obj]
    if not isinstance(obj, dict):
        return obj

    if INCLUDE_KEY not in obj:
        return {
            key: resolve_includes(value, base_path, root_dir, depth)
            for key, value in obj.items()
        }

    include_raw = obj.get(INCLUDE_KEY)
    include_list: list[str]
    if isinstance(include_raw, str):
        include_list = [include_raw]
    elif isinstance(include_raw, list) and all(isinstance(item, str) for item in include_raw):
        include_list = include_raw
    else:
        raise ValueError("$include must be string or string[]")

    merged: Any = {}
    for rel in include_list:
        include_path = (base_path.parent / rel).resolve()
        include_path = _ensure_include_inside(root_dir, include_path)
        if not include_path.exists() or not include_path.is_file():
            raise ValueError(f"include file not found: {include_path}")
        if include_path.stat().st_size > MAX_INCLUDE_FILE_BYTES:
            raise ValueError(f"include file too large: {include_path}")
        included = _parse_json(include_path.read_text(encoding="utf-8"))
        resolved = resolve_includes(included, include_path, root_dir, depth + 1)
        merged = _deep_merge(merged, resolved)

    sibling = {
        key: resolve_includes(value, base_path, root_dir, depth)
        for key, value in obj.items()
        if key != INCLUDE_KEY
    }
    return _deep_merge(merged, sibling)
