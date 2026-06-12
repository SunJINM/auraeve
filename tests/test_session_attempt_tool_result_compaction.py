from __future__ import annotations

import unittest

from auraeve.agent_runtime.compaction import clear_tool_results
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

    def test_clear_tool_results_replaces_old_large_tool_outputs_only(self) -> None:
        messages = [
            {"role": "tool", "tool_call_id": "old", "name": "read", "content": "a" * 1000},
            {"role": "assistant", "content": "继续"},
            {"role": "tool", "tool_call_id": "recent", "name": "read", "content": "b" * 1000},
        ]

        cleared = clear_tool_results(messages, keep_recent=1, min_chars=600)

        self.assertIn("工具结果已清理", cleared[0]["content"])
        self.assertEqual(cleared[0]["tool_call_id"], "old")
        self.assertEqual(cleared[2]["content"], "b" * 1000)


if __name__ == "__main__":
    unittest.main()
