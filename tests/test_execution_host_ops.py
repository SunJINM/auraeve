from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from auraeve.execution.host_ops import (
    execute_shell_command,
    list_dir,
    read_file,
    write_file,
)


class HostOpsFsTests(unittest.TestCase):
    def test_read_write_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "a" / "b.txt"

            write_res = write_file(path=str(target), content="hello", allowed_dir=root)
            self.assertEqual(write_res, ("create", None))

            read_res = read_file(path=str(target), allowed_dir=root, offset=0, limit=1)
            self.assertEqual(read_res, "1\thello")

            ls_res = list_dir(path=str(root / "a"), allowed_dir=root)
            self.assertIn("b.txt", ls_res)

    def test_allowed_dir_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root.parent / "outside-host-ops-test.txt"
            outside.write_text("x", encoding="utf-8")
            try:
                with self.assertRaises(PermissionError):
                    _ = read_file(path=str(outside), allowed_dir=root)
            finally:
                outside.unlink(missing_ok=True)

    def test_execute_shell_command_fallback_when_working_dir_invalid(self) -> None:
        result = asyncio.run(
            execute_shell_command(
                command="echo hello",
                working_dir="/app/workspace",
                timeout=5,
            )
        )
        self.assertIn("fallback", result)
        self.assertNotIn("traceback", result.lower())


if __name__ == "__main__":
    unittest.main()
