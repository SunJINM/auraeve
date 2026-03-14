from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from auraeve.skill_system.service import install_skill_from_clawhub


class SkillHubInstallSourceTests(unittest.TestCase):
    def test_install_from_tencent_skillhub_url(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auraeve-skillhub-") as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            calls: list[list[str]] = []

            def _fake_run(argv_tail: list[str]) -> dict:
                calls.append(list(argv_tail))
                candidate = argv_tail[1] if len(argv_tail) > 1 else ""
                if candidate == "owner-x/skill-y":
                    return {"ok": True, "code": 0, "stdout": "ok", "stderr": ""}
                return {"ok": False, "code": 1, "stdout": "", "stderr": "not found"}

            with patch("auraeve.skill_system.service._run_skillhub_with_fallback", side_effect=_fake_run):
                result = install_skill_from_clawhub(
                    workspace,
                    "https://skillhub.tencent.com/owner-x/skill-y",
                    force=True,
                )

            self.assertTrue(result.get("ok"))
            self.assertEqual(result.get("provider"), "skillhub.tencent")
            self.assertEqual(result.get("slug"), "owner-x/skill-y")
            self.assertIn("SkillHub Tencent", str(result.get("message")))
            self.assertGreaterEqual(len(calls), 2)
            self.assertEqual(calls[0][0], "install")
            self.assertEqual(calls[1][1], "owner-x/skill-y")

    def test_install_from_clawhub_slug_still_works(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auraeve-clawhub-") as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)

            with patch(
                "auraeve.skill_system.service._run_clawhub_with_fallback",
                return_value={"ok": True, "code": 0, "stdout": "ok", "stderr": ""},
            ):
                result = install_skill_from_clawhub(workspace, "demo-owner/demo-skill")

            self.assertTrue(result.get("ok"))
            self.assertEqual(result.get("provider"), "clawhub")
            self.assertIn("ClawHub", str(result.get("message")))

    def test_install_from_skillhub_command_text(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auraeve-skillhub-cmd-") as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            skillhub_calls: list[list[str]] = []

            def _fake_skillhub(argv_tail: list[str]) -> dict:
                skillhub_calls.append(list(argv_tail))
                return {"ok": True, "code": 0, "stdout": "ok", "stderr": ""}

            with (
                patch("auraeve.skill_system.service._run_skillhub_with_fallback", side_effect=_fake_skillhub),
                patch("auraeve.skill_system.service._run_clawhub_with_fallback", return_value={"ok": False, "code": 1, "stdout": "", "stderr": "skip"}),
            ):
                result = install_skill_from_clawhub(workspace, "skillhub install nano-banana-pro")

            self.assertTrue(result.get("ok"))
            self.assertEqual(result.get("provider"), "skillhub.tencent")
            self.assertEqual(result.get("slug"), "nano-banana-pro")
            self.assertEqual(len(skillhub_calls), 1)
            self.assertEqual(skillhub_calls[0][0], "install")
            self.assertEqual(skillhub_calls[0][1], "nano-banana-pro")

    def test_auto_fallback_from_clawhub_to_skillhub(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auraeve-skillhub-auto-") as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)

            with (
                patch("auraeve.skill_system.service._run_clawhub_with_fallback", return_value={"ok": False, "code": 1, "stdout": "", "stderr": "not found"}),
                patch("auraeve.skill_system.service._run_skillhub_with_fallback", return_value={"ok": True, "code": 0, "stdout": "ok", "stderr": ""}),
            ):
                result = install_skill_from_clawhub(workspace, "nano-banana-pro")

            self.assertTrue(result.get("ok"))
            self.assertEqual(result.get("provider"), "skillhub.tencent")
            self.assertEqual(result.get("slug"), "nano-banana-pro")


if __name__ == "__main__":
    unittest.main()
