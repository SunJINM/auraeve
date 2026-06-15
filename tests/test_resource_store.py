from __future__ import annotations

import base64

from auraeve import resource_store


def test_save_image_bytes_creates_resource_ref_under_state_resources(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURAEVE_STATE_DIR", str(tmp_path))

    ref = resource_store.save_image_bytes(b"fake image", mime="image/png", prompt="太阳")

    assert ref["kind"] == "image"
    assert ref["ref"] == f"media://{ref['id']}"
    assert ref["url"] == f"/api/webui/resources/{ref['id']}/content"
    assert ref["displayUrl"] == f"/api/webui/resources/{ref['id']}/content"
    assert ref["downloadUrl"] == f"/api/webui/resources/{ref['id']}/download"
    assert ref["prompt"] == "太阳"
    assert (tmp_path / "resources" / "images" / ref["filename"]).read_bytes() == b"fake image"


def test_refs_from_images_field_uses_resource_refs(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURAEVE_STATE_DIR", str(tmp_path))
    b64 = base64.b64encode(b"fake image").decode()

    refs = resource_store.refs_from_images_field([{"b64_json": b64}], prompt="城市")

    assert len(refs) == 1
    assert refs[0]["ref"].startswith("media://")
    assert refs[0]["url"].startswith("/api/webui/resources/")
    assert resource_store.resolve_resource_path(refs[0]["ref"]) is not None
