from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass


@dataclass
class _CacheItem:
    text: str
    expire_at: float


class STTCache:
    def __init__(self) -> None:
        self._store: dict[str, _CacheItem] = {}

    def make_key(self, file_bytes: bytes, language: str, profile: str) -> str:
        h = hashlib.sha256()
        h.update(file_bytes)
        h.update(language.encode("utf-8", errors="ignore"))
        h.update(profile.encode("utf-8", errors="ignore"))
        return h.hexdigest()

    def get(self, key: str) -> str | None:
        item = self._store.get(key)
        if item is None:
            return None
        if item.expire_at < time.time():
            self._store.pop(key, None)
            return None
        return item.text

    def set(self, key: str, text: str, ttl_s: int) -> None:
        self._store[key] = _CacheItem(text=text, expire_at=time.time() + max(ttl_s, 1))

