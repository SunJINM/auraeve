from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

cli_app = import_module("auraeve.cli.app")


def test_runtime_startup_creates_missing_config_without_exiting() -> None:
    missing = SimpleNamespace(exists=False)
    created = SimpleNamespace(exists=True, valid=True, path="config.json")

    with patch.object(cli_app.cfg, "read_snapshot", return_value=missing), patch.object(
        cli_app.cfg,
        "ensure_config_file",
        return_value=created,
    ):
        cli_app._ensure_runtime_for_run()


def test_runtime_startup_allows_missing_primary_model_api_key() -> None:
    snapshot = SimpleNamespace(
        exists=True,
        valid=True,
        path="config.json",
        issues=[],
        warnings=[],
        config={
            "LLM_MODELS": [
                {
                    "id": "main",
                    "enabled": True,
                    "isPrimary": True,
                    "apiKey": "",
                }
            ]
        },
    )

    with patch.object(cli_app.cfg, "read_snapshot", return_value=snapshot):
        cli_app._ensure_runtime_for_run()
