from __future__ import annotations

from auraeve.config.defaults import build_defaults


def test_default_config_enables_only_webui_channel() -> None:
    defaults = build_defaults()

    assert defaults["WEBUI_ENABLED"] is True
    assert defaults["NAPCAT_ENABLED"] is False
    assert defaults["DINGTALK_ENABLED"] is False
