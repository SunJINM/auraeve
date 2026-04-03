from __future__ import annotations

import sys
import types

import auraeve.config  # noqa: F401

from auraeve.providers.base import ContextOverflowError

sys.modules.setdefault("json_repair", types.SimpleNamespace(loads=lambda value: value))

from auraeve.providers.openai_provider import _classify_openai_error


def test_classify_openai_error_maps_413_to_context_overflow() -> None:
    error = Exception(
        "<html><head><title>413 Request Entity Too Large</title></head><body></body></html>"
    )

    classified = _classify_openai_error(error)

    assert isinstance(classified, ContextOverflowError)
