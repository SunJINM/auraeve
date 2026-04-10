from __future__ import annotations

import unittest

from auraeve.agent_runtime.session_attempt import _compact_tool_result


class ToolResultCompactionTests(unittest.TestCase):
    def test_compact_replaces_data_url(self) -> None:
        raw = "data:image/png;base64," + ("A" * 4000)
        compacted = _compact_tool_result("browser", raw)
        self.assertIn("inline-data-url omitted", compacted)
        self.assertNotIn("base64,", compacted)

    def test_compact_replaces_base64_uri(self) -> None:
        raw = "上传结果：base64://" + ("B" * 5000)
        compacted = _compact_tool_result("napcat_send_voice", raw)
        self.assertIn("inline-base64-uri omitted", compacted)
        self.assertNotIn("base64://BBBB", compacted)

    def test_compact_preserves_very_long_text_without_truncation(self) -> None:
        raw = "x" * 20000
        compacted = _compact_tool_result("web_fetch", raw)
        self.assertEqual(compacted, raw)


if __name__ == "__main__":
    unittest.main()
