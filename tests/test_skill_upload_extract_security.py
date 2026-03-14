from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from auraeve.skill_system.install_sources import extract_archive_safe


class SkillUploadExtractSecurityTests(unittest.TestCase):
    def test_reject_zip_slip_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auraeve-skill-sec-") as td:
            root = Path(td)
            archive = root / "malicious.zip"
            staging = root / "staging"
            outside = root / "evil.txt"

            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("../evil.txt", "owned")

            with self.assertRaises(ValueError):
                extract_archive_safe(archive, staging)

            self.assertFalse(outside.exists())


if __name__ == "__main__":
    unittest.main()
