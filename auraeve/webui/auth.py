from __future__ import annotations

from fastapi import Header, HTTPException, Query


def verify_token(expected_token: str):
    async def _verify(
        x_webui_token: str | None = Header(default=None),
        token: str | None = Query(default=None),
    ) -> None:
        if not expected_token:
            return
        actual = (x_webui_token or token or "").strip()
        if actual != expected_token:
            raise HTTPException(status_code=401, detail="未授权")

    return _verify
