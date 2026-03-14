import asyncio

from auraeve.bus.events import FileAttachment
from auraeve.bus.queue import MessageBus
from auraeve.channels.napcat import NapCatChannel, NapCatConfig


def _build_channel() -> NapCatChannel:
    return NapCatChannel(NapCatConfig(), MessageBus())


def test_extract_image_url_from_file_field() -> None:
    channel = _build_channel()
    text, media, attachments = channel._extract_content(
        [{"type": "image", "data": {"file": "https://example.com/screenshot.png"}}]
    )

    assert text == ""
    assert media == ["https://example.com/screenshot.png"]
    assert len(attachments) == 1
    assert attachments[0].url == "https://example.com/screenshot.png"
    assert attachments[0].mime_type == "image/*"


def test_extract_file_url_from_file_field() -> None:
    channel = _build_channel()
    text, media, attachments = channel._extract_content(
        [{"type": "file", "data": {"file": "https://example.com/report.pdf", "file_size": 123}}]
    )

    assert text == ""
    assert media == []
    assert len(attachments) == 1
    assert attachments[0].url == "https://example.com/report.pdf"
    assert attachments[0].filename == "report.pdf"
    assert attachments[0].size == 123


def test_extract_file_id_placeholder_still_supported() -> None:
    channel = _build_channel()
    text, media, attachments = channel._extract_content(
        [{"type": "file", "data": {"name": "archive.zip", "file_id": "abc123"}}]
    )

    assert text == ""
    assert media == []
    assert len(attachments) == 1
    assert attachments[0].filename == "archive.zip"
    assert attachments[0].url == "__file_id__:abc123"


def test_extract_image_prefers_get_image_placeholder_when_file_id_available() -> None:
    channel = _build_channel()
    text, media, attachments = channel._extract_content(
        [
            {
                "type": "image",
                "data": {
                    "url": "https://example.com/cdn.png",
                    "file": "a1b2c3d4ef.png",
                },
            }
        ]
    )

    assert text == ""
    assert media == ["https://example.com/cdn.png"]
    assert len(attachments) == 1
    assert attachments[0].url == "__image_file__:a1b2c3d4ef.png"


def test_resolve_image_placeholder_via_get_image() -> None:
    channel = _build_channel()

    async def _fake_call_action(action: str, params: dict) -> dict:
        assert action == "get_image"
        assert params == {"file": "a1b2c3d4ef.png"}
        return {"file": "/tmp/qq/a1b2c3d4ef.png"}

    channel._call_action = _fake_call_action  # type: ignore[method-assign]
    resolved = asyncio.run(
        channel._resolve_file_attachments(
            [FileAttachment(filename="image", url="__image_file__:a1b2c3d4ef.png", mime_type="image/*")]
        )
    )
    assert len(resolved) == 1
    assert resolved[0].url == "/tmp/qq/a1b2c3d4ef.png"


def test_extract_record_with_file_token() -> None:
    channel = _build_channel()
    text, media, attachments = channel._extract_content(
        [{"type": "record", "data": {"file": "voice_abc123.silk"}}]
    )

    assert text == "[语音]"
    assert media == []
    assert len(attachments) == 1
    assert attachments[0].url == "__record_file__:voice_abc123.silk"
    assert attachments[0].mime_type == "audio/*"


def test_resolve_record_placeholder_via_get_record() -> None:
    channel = _build_channel()

    async def _fake_call_action_with_retry(action: str, params: dict) -> dict:
        assert action == "get_record"
        assert params == {"file": "voice_abc123.silk", "out_format": "mp3"}
        return {"file": "/tmp/qq/voice_abc123.mp3"}

    channel._call_action_with_retry = _fake_call_action_with_retry  # type: ignore[method-assign]
    resolved = asyncio.run(
        channel._resolve_file_attachments(
            [FileAttachment(filename="voice", url="__record_file__:voice_abc123.silk", mime_type="audio/*")]
        )
    )
    assert len(resolved) == 1
    assert resolved[0].url == "/tmp/qq/voice_abc123.mp3"


def test_build_content_marks_image_when_only_attachment_present() -> None:
    channel = _build_channel()
    content = channel._build_content(
        text="",
        image_urls=[],
        attachments=[FileAttachment(filename="image.png", url="/tmp/image.png", mime_type="image/png")],
    )
    assert content == "[图片]"


def test_build_content_marks_audio_when_only_attachment_present() -> None:
    channel = _build_channel()
    content = channel._build_content(
        text="",
        image_urls=[],
        attachments=[FileAttachment(filename="voice.mp3", url="/tmp/voice.mp3", mime_type="audio/mpeg")],
    )
    assert content == "[语音]"

