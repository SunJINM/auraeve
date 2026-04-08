from __future__ import annotations

from copy import deepcopy

from auraeve.config.defaults import build_defaults
from auraeve.config.schema import validate_config_object


def test_validate_config_accepts_single_primary_model_and_asr_object() -> None:
    cfg = build_defaults()
    ok, issues = validate_config_object(cfg)
    assert ok is True
    assert issues == []


def test_validate_config_rejects_missing_primary_model() -> None:
    cfg = build_defaults()
    cfg["LLM_MODELS"][0]["isPrimary"] = False
    ok, issues = validate_config_object(cfg)
    assert ok is False
    assert any(issue["path"] == "LLM_MODELS" for issue in issues)
    assert any("primary" in issue["message"].lower() for issue in issues)


def test_validate_config_rejects_multiple_primary_models() -> None:
    cfg = build_defaults()
    second = deepcopy(cfg["LLM_MODELS"][0])
    second["id"] = "backup"
    second["label"] = "Backup"
    second["isPrimary"] = True
    cfg["LLM_MODELS"].append(second)
    ok, issues = validate_config_object(cfg)
    assert ok is False
    assert any(issue["path"] == "LLM_MODELS" for issue in issues)
    assert any("exactly one" in issue["message"].lower() for issue in issues)


def test_validate_config_rejects_unknown_capability_flag() -> None:
    cfg = build_defaults()
    cfg["LLM_MODELS"][0]["capabilities"]["visionMode"] = True
    ok, issues = validate_config_object(cfg)
    assert ok is False
    assert any(issue["path"] == "LLM_MODELS[0].capabilities.visionMode" for issue in issues)
