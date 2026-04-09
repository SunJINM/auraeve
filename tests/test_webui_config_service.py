from __future__ import annotations

from auraeve.config.defaults import build_defaults
from auraeve.webui.config_service import ConfigService
import auraeve.config as cfg


def test_config_service_set_preserves_masked_nested_api_keys(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AURAEVE_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("AURAEVE_CONFIG_PATH", raising=False)

    initial = build_defaults()
    initial["LLM_MODELS"][0]["apiKey"] = "model-secret"
    initial["ASR"]["providers"][0]["apiKey"] = "asr-secret"
    ok, snapshot, _changed, _restart, issues = cfg.write(initial)
    assert ok is True, issues

    service = ConfigService()
    current = service.get()
    assert current.config["LLM_MODELS"][0]["apiKey"] == "********"
    assert current.config["ASR"]["providers"][0]["apiKey"] == "********"

    payload = current.config
    payload["LLM_MODELS"][0]["label"] = "更新后的主模型"
    payload["ASR"]["providers"][0]["priority"] = 321

    result = service.set(current.baseHash, payload)
    assert result.ok is True, result.issues

    next_snapshot = cfg.read_snapshot()
    assert next_snapshot.config["LLM_MODELS"][0]["apiKey"] == "model-secret"
    assert next_snapshot.config["ASR"]["providers"][0]["apiKey"] == "asr-secret"
