from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from auraeve.execution.host_ops import (
    ShellCommandResult,
    execute_shell_command,
    guard_shell_command,
    posix_path_to_windows_path,
    read_file,
    windows_path_to_posix_path,
    write_file,
)


class HostOpsFsTests(unittest.TestCase):
    def test_read_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "a" / "b.txt"

            write_res = write_file(path=str(target), content="hello", allowed_dir=root)
            self.assertEqual(write_res, ("create", None))

            read_res = read_file(path=str(target), allowed_dir=root, offset=0, limit=1)
            self.assertEqual(read_res, "1\thello")

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
                timeout_ms=5_000,
            )
        )
        self.assertIsInstance(result, ShellCommandResult)
        self.assertIn("fallback", result.stderr)
        self.assertNotIn("traceback", result.stderr.lower())

    def test_windows_path_roundtrip_for_git_bash(self) -> None:
        original = r"D:\WorkProjects\auraeve\foo\bar.txt"
        posix = windows_path_to_posix_path(original)

        self.assertEqual(posix, "/d/WorkProjects/auraeve/foo/bar.txt")
        self.assertEqual(posix_path_to_windows_path(posix), original)

    def test_guard_shell_command_blocks_destructive_git_operations(self) -> None:
        blocked = guard_shell_command("git reset --hard HEAD~1", os.getcwd())
        self.assertIsNotNone(blocked)
        self.assertIn("blocked", blocked or "")


if __name__ == "__main__":
    unittest.main()
