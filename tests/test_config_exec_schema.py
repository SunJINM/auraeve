from __future__ import annotations

import unittest

from auraeve.config.defaults import DEFAULTS
from auraeve.config.schema import validate_config_object


class ConfigExecSchemaTests(unittest.TestCase):
    def test_executor_legacy_keys_are_rejected(self) -> None:
        payload = dict(DEFAULTS)
        payload["EXEC_HOST"] = "host"
        ok, issues = validate_config_object(payload)
        self.assertFalse(ok)
        self.assertTrue(any(i.get("path") == "EXEC_HOST" for i in issues))

    def test_executor_port_legacy_key_is_rejected(self) -> None:
        payload = dict(DEFAULTS)
        payload["EXECUTOR_PORT"] = 70000
        ok, issues = validate_config_object(payload)
        self.assertFalse(ok)
        self.assertTrue(any(i.get("path") == "EXECUTOR_PORT" for i in issues))

    def test_executor_url_legacy_key_is_rejected(self) -> None:
        payload = dict(DEFAULTS)
        payload["EXECUTOR_URL"] = "http://127.0.0.1:18791"
        ok, issues = validate_config_object(payload)
        self.assertFalse(ok)
        self.assertTrue(any(i.get("path") == "EXECUTOR_URL" for i in issues))


if __name__ == "__main__":
    unittest.main()
