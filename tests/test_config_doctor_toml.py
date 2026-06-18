from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from auraeve.config.doctor import run_config_doctor
from auraeve.config.io import read_config_snapshot


class ConfigDoctorTomlTests(unittest.TestCase):
    def test_doctor_fix_prunes_unknown_toml_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_state_dir = os.environ.get("AURAEVE_STATE_DIR")
            old_config_path = os.environ.get("AURAEVE_CONFIG_PATH")
            try:
                os.environ["AURAEVE_STATE_DIR"] = temp_dir
                os.environ.pop("AURAEVE_CONFIG_PATH", None)

                cfg_path = Path(temp_dir) / "auraeve.toml"
                cfg_path.write_text(
                    """
UNKNOWN_KEY = true
LLM_MAX_TOOL_ITERATIONS = 10

[[LLM_MODELS]]
id = "main"
label = "主模型"
enabled = true
isPrimary = true
model = "gpt-5.4-mini"
apiKey = "test-key"
maxTokens = 4096
temperature = 0.3
thinkingBudgetTokens = 0

[LLM_MODELS.extraHeaders]

[LLM_MODELS.capabilities]
imageInput = true
audioInput = false
documentInput = true
toolCalling = true
streaming = true
""".strip()
                    + "\n",
                    encoding="utf-8",
                )

                report = run_config_doctor(fix=True)
                self.assertTrue(report.get("ok"), report)

                snapshot = read_config_snapshot()
                self.assertTrue(snapshot.valid, snapshot.issues)
                self.assertEqual(snapshot.config["LLM_MAX_TOOL_ITERATIONS"], 10)
                self.assertNotIn("UNKNOWN_KEY", snapshot.resolved)
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
