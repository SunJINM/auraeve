from __future__ import annotations

from fastapi import UploadFile

from auraeve.skill_system.install_sources import save_uploaded_archive_bytes


class UploadWebService:
    async def upload_skill_archive(self, file: UploadFile) -> dict:
        filename = file.filename or "skill-archive"
        payload = await file.read()
        return save_uploaded_archive_bytes(filename, payload)
