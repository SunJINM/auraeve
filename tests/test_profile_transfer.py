from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from auraeve.profile_transfer import export_profile_archive, import_profile_archive


class ProfileTransferTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmp = Path(tempfile.mkdtemp(prefix="auraeve-profile-test-"))
        self.state_dir = self._tmp / "state"
        os.environ["AURAEVE_STATE_DIR"] = str(self.state_dir)
        os.environ.pop("AURAEVE_CONFIG_PATH", None)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _seed_state(self) -> None:
        (self.state_dir / "workspace" / "memory").mkdir(parents=True, exist_ok=True)
        (self.state_dir / "skills").mkdir(parents=True, exist_ok=True)
        (self.state_dir / "plugins").mkdir(parents=True, exist_ok=True)
        (self.state_dir / "workspace" / "memory" / "MEMORY.md").write_text(
            "# long memory\n- foo\n",
            encoding="utf-8",
        )
        (self.state_dir / "workspace" / "memory" / "2026-03-14.md").write_text(
            "# daily\n- bar\n",
            encoding="utf-8",
        )
        (self.state_dir / "skills" / "state.json").write_text('{"entries":{"demo":{"enabled":true}}}\n', encoding="utf-8")
        (self.state_dir / "plugins" / "state.json").write_text('{"entries":{"p.demo":{"enabled":true}}}\n', encoding="utf-8")
        (self.state_dir / "memory.db").write_bytes(b"sqlite-bytes")
        (self.state_dir / "auraeve.json").write_text('{"LLM_API_KEY":"test-key"}\n', encoding="utf-8")

    def test_export_import_roundtrip(self) -> None:
        self._seed_state()
        archive = self._tmp / "profile.auraeve"

        exported = export_profile_archive(archive)
        self.assertTrue(archive.exists())
        self.assertGreater(exported["files"], 0)

        shutil.rmtree(self.state_dir, ignore_errors=True)
        imported = import_profile_archive(archive, force=True)
        self.assertTrue(imported["ok"])

        self.assertTrue((self.state_dir / "auraeve.json").exists())
        self.assertTrue((self.state_dir / "memory.db").exists())
        self.assertTrue((self.state_dir / "workspace" / "memory" / "MEMORY.md").exists())
        self.assertTrue((self.state_dir / "skills" / "state.json").exists())
        self.assertTrue((self.state_dir / "plugins" / "state.json").exists())

    def test_import_requires_force_when_target_not_empty(self) -> None:
        self._seed_state()
        archive = self._tmp / "profile.auraeve"
        export_profile_archive(archive)

        (self.state_dir / "workspace" / "memory" / "extra.md").write_text("x\n", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            import_profile_archive(archive, force=False)


if __name__ == "__main__":
    unittest.main()
