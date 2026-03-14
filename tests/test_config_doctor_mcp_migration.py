from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from auraeve.config.doctor import run_config_doctor
from auraeve.config.io import read_config_snapshot


class ConfigDoctorMCPMigrationTests(unittest.TestCase):
    def test_doctor_fix_migrates_legacy_mcp_keys(self) -> None:
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
                            "MCP_SERVERS": {
                                "fs-main": {
                                    "command": "npx",
                                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
                                    "env": {"NODE_ENV": "production"},
                                }
                            },
                            "MCP_HOT_RELOAD_ENABLED": False,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                report = run_config_doctor(fix=True)
                self.assertTrue(report.get("ok"), report)

                snapshot = read_config_snapshot()
                self.assertTrue(snapshot.valid, snapshot.issues)
                self.assertIn("MCP", snapshot.resolved)
                self.assertNotIn("MCP_SERVERS", snapshot.resolved)
                self.assertNotIn("MCP_HOT_RELOAD_ENABLED", snapshot.resolved)

                mcp = snapshot.resolved.get("MCP")
                self.assertIsInstance(mcp, dict)
                if isinstance(mcp, dict):
                    self.assertEqual(mcp.get("reloadPolicy"), "none")
                    servers = mcp.get("servers")
                    self.assertIsInstance(servers, dict)
                    if isinstance(servers, dict):
                        self.assertIn("fs-main", servers)
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

