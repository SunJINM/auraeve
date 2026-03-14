from __future__ import annotations

import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from auraeve.config.paths import resolve_state_dir
from auraeve.skill_system.install_sources import install_skills_from_uploaded_archive, save_uploaded_archive_bytes


def _build_skill_archive_bytes(*, body: str) -> bytes:
    buf = io.BytesIO()
    content = (
        "---\n"
        "name: demo-skill\n"
        "description: demo skill\n"
        'metadata: {"auraeve":{"skillKey":"demo.skill"}}\n'
        "---\n\n"
        f"{body}\n"
    )
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("demo-skill/SKILL.md", content)
    return buf.getvalue()


class SkillInstallFromUploadTests(unittest.TestCase):
    def test_install_from_uploaded_archive(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auraeve-skill-upload-") as td:
            with patch.dict(os.environ, {"AURAEVE_STATE_DIR": td}, clear=False):
                uploaded = save_uploaded_archive_bytes("demo.zip", _build_skill_archive_bytes(body="v1"))
                self.assertTrue(uploaded.get("ok"))

                result = install_skills_from_uploaded_archive(str(uploaded.get("uploadId")))
                self.assertTrue(result.get("ok"))
                self.assertEqual(len(result.get("installed") or []), 1)

                managed_dir = resolve_state_dir() / "skills" / "managed"
                self.assertTrue(managed_dir.exists())
                installed_skill_files = list(managed_dir.rglob("SKILL.md"))
                self.assertEqual(len(installed_skill_files), 1)
                text = installed_skill_files[0].read_text(encoding="utf-8")
                self.assertIn("v1", text)

    def test_conflict_and_force_overwrite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auraeve-skill-upload-force-") as td:
            with patch.dict(os.environ, {"AURAEVE_STATE_DIR": td}, clear=False):
                first = save_uploaded_archive_bytes("demo.zip", _build_skill_archive_bytes(body="v1"))
                self.assertTrue(first.get("ok"))
                first_install = install_skills_from_uploaded_archive(str(first.get("uploadId")))
                self.assertTrue(first_install.get("ok"))

                second = save_uploaded_archive_bytes("demo.zip", _build_skill_archive_bytes(body="v2"))
                self.assertTrue(second.get("ok"))
                conflict = install_skills_from_uploaded_archive(str(second.get("uploadId")), force=False)
                self.assertFalse(conflict.get("ok"))
                self.assertEqual(len(conflict.get("skipped") or []), 1)

                third = save_uploaded_archive_bytes("demo.zip", _build_skill_archive_bytes(body="v3"))
                self.assertTrue(third.get("ok"))
                forced = install_skills_from_uploaded_archive(str(third.get("uploadId")), force=True)
                self.assertTrue(forced.get("ok"))
                self.assertEqual(len(forced.get("installed") or []), 1)

                managed_dir = resolve_state_dir() / "skills" / "managed"
                installed_skill_files = list(managed_dir.rglob("SKILL.md"))
                self.assertEqual(len(installed_skill_files), 1)
                text = installed_skill_files[0].read_text(encoding="utf-8")
                self.assertIn("v3", text)


if __name__ == "__main__":
    unittest.main()
