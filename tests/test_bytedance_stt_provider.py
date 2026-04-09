from __future__ import annotations

import base64
from pathlib import Path

import pytest

from auraeve.stt.providers.factory import build_provider
import httpx

from auraeve.stt.types import AuthError, ProviderProfile, STTRequest, TransientError


def _profile() -> ProviderProfile:
    return ProviderProfile(
        id="volc-main",
        enabled=True,
        priority=100,
        type="bytedance-flash",
        model="bigmodel",
        api_base="https://openspeech.bytedance.com",
        api_key="volc-key",
        timeout_ms=8000,
        options={
            "resourceId": "volc.bigasr.auc_turbo",
            "uid": "user-123",
        },
    )


def test_factory_builds_bytedance_flash_provider_from_type() -> None:
    provider = build_provider(_profile())
    assert provider is not None
    assert provider.__class__.__name__ == "ByteDanceFlashSTTProvider"


@pytest.mark.asyncio
async def test_bytedance_flash_provider_transcribes_local_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audio_path = tmp_path / "demo.wav"
    audio_path.write_bytes(b"audio-bytes")
    captured: dict[str, object] = {}

    class _FakeResponse:
        headers = {
            "X-Api-Status-Code": "20000000",
            "X-Api-Message": "OK",
            "X-Tt-Logid": "logid-1",
        }

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "audio_info": {"duration": 1200},
                "result": {
                    "text": "本地音频识别成功",
                    "utterances": [
                        {"start_time": 0, "end_time": 1200, "text": "本地音频识别成功"},
                    ],
                },
            }

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _FakeResponse()

    monkeypatch.setattr("auraeve.stt.providers.bytedance_flash.httpx.AsyncClient", _FakeClient)

    provider = build_provider(_profile())
    assert provider is not None
    result = await provider.transcribe(
        STTRequest(input_path=audio_path, channel="read", language="zh-CN")
    )

    assert result.ok is True
    assert result.text == "本地音频识别成功"
    assert captured["url"] == "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["X-Api-Key"] == "volc-key"
    assert headers["X-Api-Resource-Id"] == "volc.bigasr.auc_turbo"
    assert headers["X-Api-Sequence"] == "-1"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["user"] == {"uid": "user-123"}
    assert payload["request"] == {"model_name": "bigmodel"}
    audio = payload["audio"]
    assert isinstance(audio, dict)
    assert audio["data"] == base64.b64encode(b"audio-bytes").decode("utf-8")


@pytest.mark.asyncio
async def test_bytedance_flash_provider_prefers_ogg_opus_for_local_m4a(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_path = tmp_path / "demo.m4a"
    audio_path.write_bytes(b"m4a-bytes")
    converted_path = tmp_path / "demo.ogg"
    converted_path.write_bytes(b"ogg-opus-bytes")
    captured: dict[str, object] = {}

    async def _fake_normalize(input_path: str) -> tuple[str, bool, str]:
        assert input_path == str(audio_path)
        return str(converted_path), True, "ogg"

    class _FakeResponse:
        headers = {
            "X-Api-Status-Code": "20000000",
            "X-Api-Message": "OK",
            "X-Tt-Logid": "logid-1b",
        }

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "audio_info": {"duration": 1200},
                "result": {
                    "text": "m4a 转写成功",
                    "utterances": [
                        {"start_time": 0, "end_time": 1200, "text": "m4a 转写成功"},
                    ],
                },
            }

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _FakeResponse()

    monkeypatch.setattr(
        "auraeve.stt.providers.bytedance_flash.normalize_for_bytedance_flash_upload",
        _fake_normalize,
        raising=False,
    )
    monkeypatch.setattr("auraeve.stt.providers.bytedance_flash.httpx.AsyncClient", _FakeClient)

    provider = build_provider(_profile())
    assert provider is not None
    result = await provider.transcribe(
        STTRequest(input_path=audio_path, channel="read", language="zh-CN")
    )

    assert result.ok is True
    payload = captured["json"]
    assert isinstance(payload, dict)
    audio = payload["audio"]
    assert isinstance(audio, dict)
    assert audio["data"] == base64.b64encode(b"ogg-opus-bytes").decode("utf-8")


@pytest.mark.asyncio
async def test_bytedance_flash_provider_transcribes_audio_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeResponse:
        headers = {
            "X-Api-Status-Code": "20000000",
            "X-Api-Message": "OK",
            "X-Tt-Logid": "logid-2",
        }

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "audio_info": {"duration": 2100},
                "result": {
                    "text": "",
                    "utterances": [
                        {"start_time": 0, "end_time": 1000, "text": "网络音频"},
                        {"start_time": 1000, "end_time": 2100, "text": "识别成功"},
                    ],
                },
            }

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _FakeResponse()

    monkeypatch.setattr("auraeve.stt.providers.bytedance_flash.httpx.AsyncClient", _FakeClient)

    provider = build_provider(_profile())
    assert provider is not None
    result = await provider.transcribe(
        STTRequest(
            input_path=Path("placeholder.wav"),
            channel="read",
            language="zh-CN",
            audio_url="https://example.com/demo.ogg",
        )
    )

    assert result.ok is True
    assert result.text == "网络音频\n识别成功"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["audio"] == {"url": "https://example.com/demo.ogg"}


@pytest.mark.asyncio
async def test_bytedance_flash_provider_raises_on_api_status_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audio_path = tmp_path / "demo.wav"
    audio_path.write_bytes(b"audio-bytes")

    class _FakeResponse:
        headers = {
            "X-Api-Status-Code": "55000031",
            "X-Api-Message": "server busy",
            "X-Tt-Logid": "logid-3",
        }

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"error": "busy"}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
            return _FakeResponse()

    monkeypatch.setattr("auraeve.stt.providers.bytedance_flash.httpx.AsyncClient", _FakeClient)

    provider = build_provider(_profile())
    assert provider is not None
    with pytest.raises(TransientError):
        await provider.transcribe(STTRequest(input_path=audio_path, channel="read"))


@pytest.mark.asyncio
async def test_bytedance_flash_provider_maps_auth_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audio_path = tmp_path / "demo.wav"
    audio_path.write_bytes(b"audio-bytes")

    class _FakeResponse:
        status_code = 401
        headers = {
            "X-Api-Status-Code": "40100000",
            "X-Api-Message": "unauthorized",
            "X-Tt-Logid": "logid-4",
        }

        def json(self) -> dict[str, object]:
            return {"error": "bad key"}

        def raise_for_status(self) -> None:
            request = httpx.Request("POST", "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash")
            raise httpx.HTTPStatusError("401 unauthorized", request=request, response=self)

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
            return _FakeResponse()

    monkeypatch.setattr("auraeve.stt.providers.bytedance_flash.httpx.AsyncClient", _FakeClient)

    provider = build_provider(_profile())
    assert provider is not None
    with pytest.raises(AuthError):
        await provider.transcribe(STTRequest(input_path=audio_path, channel="read"))
