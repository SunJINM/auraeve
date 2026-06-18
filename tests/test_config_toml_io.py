from __future__ import annotations

import os
import tomllib
import tempfile
import unittest
from pathlib import Path

from auraeve.cli.app import _required_config_issues
from auraeve.config.io import read_config_snapshot, write_config
from auraeve.config.paths import resolve_config_path
from auraeve.config.schema import validate_config_object


class ConfigTomlIOTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_state_dir = os.environ.get("AURAEVE_STATE_DIR")
        self._old_config_path = os.environ.get("AURAEVE_CONFIG_PATH")
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["AURAEVE_STATE_DIR"] = self._tmp.name
        os.environ.pop("AURAEVE_CONFIG_PATH", None)

    def tearDown(self) -> None:
        from auraeve.observability.manager import close_observability

        close_observability()
        if self._old_state_dir is None:
            os.environ.pop("AURAEVE_STATE_DIR", None)
        else:
            os.environ["AURAEVE_STATE_DIR"] = self._old_state_dir
        if self._old_config_path is None:
            os.environ.pop("AURAEVE_CONFIG_PATH", None)
        else:
            os.environ["AURAEVE_CONFIG_PATH"] = self._old_config_path
        self._tmp.cleanup()

    def test_default_config_path_uses_toml(self) -> None:
        self.assertEqual(resolve_config_path().name, "auraeve.toml")

    def test_read_config_snapshot_loads_toml(self) -> None:
        cfg_path = Path(self._tmp.name) / "auraeve.toml"
        cfg_path.write_text(
            """
LLM_MAX_TOOL_ITERATIONS = 12
TAVILY_API_KEY = "${AURAEVE_TEST_TAVILY_KEY}"

[[LLM_MODELS]]
id = "main"
label = "主模型"
enabled = true
isPrimary = true
model = "gpt-5.4-mini"
apiBase = "https://example.invalid/v1"
apiKey = "${AURAEVE_TEST_LLM_KEY}"
maxTokens = 4096
temperature = 0.3
thinkingBudgetTokens = 128

[LLM_MODELS.extraHeaders]
X-Test = "1"

[LLM_MODELS.capabilities]
imageInput = true
audioInput = false
documentInput = true
toolCalling = true
streaming = true

[READ_ROUTING]
imageFallbackEnabled = false
failWhenNoImageModel = false
imageToTextPrompt = "toml prompt"
""".strip()
            + "\n",
            encoding="utf-8",
        )
        os.environ["AURAEVE_TEST_TAVILY_KEY"] = "tavily-key"
        os.environ["AURAEVE_TEST_LLM_KEY"] = "llm-key"

        snapshot = read_config_snapshot()

        self.assertTrue(snapshot.valid, snapshot.issues)
        self.assertEqual(snapshot.config["LLM_MAX_TOOL_ITERATIONS"], 12)
        self.assertEqual(snapshot.config["TAVILY_API_KEY"], "tavily-key")
        self.assertEqual(snapshot.config["LLM_MODELS"][0]["apiKey"], "llm-key")
        self.assertEqual(snapshot.config["LLM_MODELS"][0]["extraHeaders"], {"X-Test": "1"})
        self.assertEqual(snapshot.config["READ_ROUTING"]["imageToTextPrompt"], "toml prompt")

    def test_write_config_persists_toml(self) -> None:
        ok, snapshot, changed, _requires_restart, issues = write_config(
            {
                "LLM_MAX_TOOL_ITERATIONS": 7,
                "LLM_MODELS": [
                    {
                        "id": "main",
                        "label": "主模型",
                        "enabled": True,
                        "isPrimary": True,
                        "model": "gpt-5.4-mini",
                        "apiBase": None,
                        "apiKey": "test-key",
                        "extraHeaders": {"X-Test": "1"},
                        "maxTokens": 4096,
                        "temperature": 0.3,
                        "thinkingBudgetTokens": 0,
                        "capabilities": {
                            "imageInput": True,
                            "audioInput": False,
                            "documentInput": True,
                            "toolCalling": True,
                            "streaming": True,
                        },
                    }
                ],
                "AGENTS_LIST": [{"id": "dev", "workspace": "D:/WorkProjects/auraeve"}],
                "SESSION_TOOL_POLICY": {"default": {"deny": ["Shell"]}},
            }
        )

        self.assertTrue(ok, issues)
        self.assertIn("LLM_MAX_TOOL_ITERATIONS", changed)
        raw = snapshot.path.read_text(encoding="utf-8")
        self.assertIn("# 配置项：LLM_MAX_TOOL_ITERATIONS", raw)
        self.assertIn("# 配置项：id", raw)
        self.assertIn('LLM_MAX_TOOL_ITERATIONS = 7', raw)
        self.assertIn("[[LLM_MODELS]]", raw)
        self.assertIn("[LLM_MODELS.capabilities]", raw)
        self.assertNotIn('"LLM_MAX_TOOL_ITERATIONS":', raw)

        reread = read_config_snapshot()
        self.assertTrue(reread.valid, reread.issues)
        self.assertEqual(reread.config["LLM_MODELS"][0]["apiKey"], "test-key")
        self.assertEqual(reread.config["AGENTS_LIST"], [{"id": "dev", "workspace": "D:/WorkProjects/auraeve"}])
        self.assertEqual(reread.config["SESSION_TOOL_POLICY"], {"default": {"deny": ["Shell"]}})

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

    def test_example_toml_is_valid_config(self) -> None:
        example_path = Path(__file__).resolve().parents[1] / "auraeve" / "config.example.toml"
        payload = tomllib.loads(example_path.read_text(encoding="utf-8"))

        ok, issues = validate_config_object(payload)

        self.assertTrue(ok, issues)


if __name__ == "__main__":
    unittest.main()
