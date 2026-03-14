from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return payload


def write_text_atomic(path: Path, content: str, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        try:
            os.chmod(tmp_name, mode)
        except Exception:
            pass
        try:
            os.replace(tmp_name, path)
        except Exception:
            Path(tmp_name).replace(path)
    finally:
        tmp_path = Path(tmp_name)
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def save_json_file_atomic(path: Path, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    write_text_atomic(path, body)
