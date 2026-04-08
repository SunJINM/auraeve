from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from auraeve.cli.app import _required_config_issues
from auraeve.config.io import read_config_snapshot


class ConfigLegacyMigrationTests(unittest.TestCase):
    def test_read_config_snapshot_accepts_legacy_llm_and_asr_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_state_dir = os.environ.get("AURAEVE_STATE_DIR")
            old_config_path = os.environ.get("AURAEVE_CONFIG_PATH")
            try:
                os.environ["AURAEVE_STATE_DIR"] = temp_dir
                os.environ.pop("AURAEVE_CONFIG_PATH", None)

                cfg_path = Path(temp_dir) / "auraeve.json"
                cfg_path.write_text(
                    json.dumps(
                        {
                            "LLM_MODEL": "gpt-5.4-mini",
                            "LLM_API_KEY": "test-key",
                            "LLM_API_BASE": "https://example.invalid/v1",
                            "LLM_EXTRA_HEADERS": {"X-Test": "1"},
                            "LLM_MAX_TOKENS": 4096,
                            "LLM_TEMPERATURE": 0.3,
                            "LLM_THINKING_BUDGET_TOKENS": 128,
                            "STT_ENABLED": True,
                            "STT_DEFAULT_LANGUAGE": "en-US",
                            "STT_TIMEOUT_MS": 9000,
                            "STT_MAX_CONCURRENCY": 2,
                            "STT_RETRY_COUNT": 3,
                            "STT_FAILOVER_ENABLED": False,
                            "STT_CACHE_ENABLED": False,
                            "STT_CACHE_TTL_S": 120,
                            "STT_PROVIDERS": [
                                {
                                    "id": "openai",
                                    "enabled": True,
                                    "priority": 5,
                                    "type": "openai",
                                    "model": "gpt-4o-mini-transcribe",
                                    "apiKey": "asr-key",
                                    "timeoutMs": 8000,
                                }
                            ],
                            "MEDIA_UNDERSTANDING": {
                                "imageFallbackEnabled": False,
                                "failWhenNoImageModel": False,
                                "imageToTextPrompt": "legacy prompt",
                            },
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                snapshot = read_config_snapshot()
                self.assertTrue(snapshot.valid, snapshot.issues)
                self.assertIn("LLM_MODELS", snapshot.resolved)
                self.assertIn("ASR", snapshot.resolved)
                self.assertIn("READ_ROUTING", snapshot.resolved)
                self.assertNotIn("LLM_MODEL", snapshot.resolved)
                self.assertNotIn("STT_ENABLED", snapshot.resolved)
                self.assertNotIn("MEDIA_UNDERSTANDING", snapshot.resolved)

                model = snapshot.config["LLM_MODELS"][0]
                self.assertEqual(model["model"], "gpt-5.4-mini")
                self.assertEqual(model["apiKey"], "test-key")
                self.assertEqual(model["apiBase"], "https://example.invalid/v1")
                self.assertEqual(model["extraHeaders"], {"X-Test": "1"})
                self.assertEqual(model["maxTokens"], 4096)
                self.assertEqual(model["temperature"], 0.3)
                self.assertEqual(model["thinkingBudgetTokens"], 128)

                asr = snapshot.config["ASR"]
                self.assertEqual(asr["defaultLanguage"], "en-US")
                self.assertEqual(asr["timeoutMs"], 9000)
                self.assertEqual(asr["maxConcurrency"], 2)
                self.assertEqual(asr["retryCount"], 3)
                self.assertFalse(asr["failoverEnabled"])
                self.assertFalse(asr["cacheEnabled"])
                self.assertEqual(asr["cacheTtlSeconds"], 120)
                self.assertEqual(asr["providers"][0]["apiKey"], "asr-key")

                routing = snapshot.config["READ_ROUTING"]
                self.assertFalse(routing["imageFallbackEnabled"])
                self.assertFalse(routing["failWhenNoImageModel"])
                self.assertEqual(routing["imageToTextPrompt"], "legacy prompt")
            finally:
                if old_state_dir is None:
                    os.environ.pop("AURAEVE_STATE_DIR", None)
                else:
                    os.environ["AURAEVE_STATE_DIR"] = old_state_dir
                if old_config_path is None:
                    os.environ.pop("AURAEVE_CONFIG_PATH", None)
                else:
                    os.environ["AURAEVE_CONFIG_PATH"] = old_config_path

    def test_required_config_issues_accepts_primary_model_api_key(self) -> None:
        snapshot = type(
            "Snapshot",
            (),
            {
                "config": {
                    "LLM_MODELS": [
                        {
                            "id": "main",
                            "label": "Main",
                            "enabled": True,
                            "isPrimary": True,
                            "model": "gpt-5.4-mini",
                            "apiKey": "test-key",
                            "capabilities": {
                                "imageInput": False,
                                "audioInput": False,
                                "documentInput": True,
                                "toolCalling": True,
                                "streaming": True,
                            },
                        }
                    ]
                }
            },
        )()

        self.assertEqual(_required_config_issues(snapshot), [])

    def test_read_config_snapshot_infers_legacy_stt_provider_types(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_state_dir = os.environ.get("AURAEVE_STATE_DIR")
            old_config_path = os.environ.get("AURAEVE_CONFIG_PATH")
            try:
                os.environ["AURAEVE_STATE_DIR"] = temp_dir
                os.environ.pop("AURAEVE_CONFIG_PATH", None)

                cfg_path = Path(temp_dir) / "auraeve.json"
                cfg_path.write_text(
                    json.dumps(
                        {
                            "LLM_API_KEY": "test-key",
                            "STT_PROVIDERS": [
                                {
                                    "id": "openai",
                                    "model": "gpt-4o-mini-transcribe",
                                    "apiKey": "asr-key",
                                },
                                {
                                    "id": "whisper-cli",
                                    "command": "whisper",
                                    "argsTemplate": ["{{input}}"],
                                },
                                {
                                    "id": "funasr-local",
                                    "model": "paraformer-zh",
                                },
                            ],
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                snapshot = read_config_snapshot()
                self.assertTrue(snapshot.valid, snapshot.issues)
                providers = snapshot.config["ASR"]["providers"]
                self.assertEqual([item["type"] for item in providers], ["openai", "whisper-cli", "funasr-local"])
            finally:
                if old_state_dir is None:
                    os.environ.pop("AURAEVE_STATE_DIR", None)
                else:
                    os.environ["AURAEVE_STATE_DIR"] = old_state_dir
                if old_config_path is None:
                    os.environ.pop("AURAEVE_CONFIG_PATH", None)
                else:
                    os.environ["AURAEVE_CONFIG_PATH"] = old_config_path


if __name__ == "__main__":
    unittest.main()
