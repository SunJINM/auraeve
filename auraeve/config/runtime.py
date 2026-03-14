from __future__ import annotations

from .schema import COLD_KEYS, HOT_KEYS


def split_hot_cold_keys(keys: list[str]) -> tuple[list[str], list[str]]:
    hot = [key for key in keys if key in HOT_KEYS]
    cold = [key for key in keys if key in COLD_KEYS]
    return hot, cold
