from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import UploadFile

import auraeve.config as cfg
from auraeve.profile_transfer import export_profile_archive, import_profile_archive


class ProfileWebService:
    def export_archive(self) -> tuple[bytes, str]:
        with tempfile.TemporaryDirectory(prefix="auraeve-webui-export-") as tmp:
            archive_path = Path(tmp) / "auraeve-profile.auraeve"
            export_profile_archive(archive_path)
            data = archive_path.read_bytes()
            return data, archive_path.name

    async def import_archive(self, file: UploadFile, *, force: bool = False) -> dict[str, Any]:
        filename = file.filename or "profile.auraeve"
        with tempfile.TemporaryDirectory(prefix="auraeve-webui-import-") as tmp:
            archive_path = Path(tmp) / filename
            content = await file.read()
            archive_path.write_bytes(content)
            result = import_profile_archive(archive_path, force=force)
        cfg.reload()
        return result
