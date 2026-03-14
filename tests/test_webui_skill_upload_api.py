from __future__ import annotations

import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from auraeve.webui.server import WebUIServer


def _skill_archive_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "demo-skill/SKILL.md",
            (
                "---\n"
                "name: demo-skill\n"
                "description: demo skill\n"
                'metadata: {"auraeve":{"skillKey":"demo.skill"}}\n'
                "---\n\n"
                "demo body\n"
            ),
        )
    return buf.getvalue()


class SkillUploadApiTests(unittest.TestCase):
    def test_upload_and_install_archive_api(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auraeve-webui-upload-") as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            with patch.dict(os.environ, {"AURAEVE_STATE_DIR": td}, clear=False):
                server = WebUIServer(
                    chat_service=MagicMock(),
                    config_service=MagicMock(),
                    token="secret",
                    workspace=workspace,
                )
                client = TestClient(server._app)
                headers = {"X-WEBUI-TOKEN": "secret"}

                upload_resp = client.post(
                    "/api/webui/skills/upload",
                    files={"file": ("demo.zip", _skill_archive_bytes(), "application/zip")},
                    headers=headers,
                )
                self.assertEqual(upload_resp.status_code, 200)
                upload_payload = upload_resp.json()
                self.assertTrue(upload_payload.get("ok"))
                self.assertTrue(upload_payload.get("uploadId"))

                install_resp = client.post(
                    "/api/webui/skills/install-upload",
                    json={"uploadId": upload_payload.get("uploadId"), "force": False},
                    headers=headers,
                )
                self.assertEqual(install_resp.status_code, 200)
                install_payload = install_resp.json()
                self.assertTrue(install_payload.get("ok"))
                self.assertEqual(len(install_payload.get("installed") or []), 1)

                list_resp = client.get("/api/webui/skills/list", headers=headers)
                self.assertEqual(list_resp.status_code, 200)
                skills = list_resp.json().get("skills") or []
                self.assertTrue(any(item.get("skillKey") == "demo.skill" for item in skills))


if __name__ == "__main__":
    unittest.main()
