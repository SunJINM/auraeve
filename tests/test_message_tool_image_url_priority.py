from __future__ import annotations

import asyncio

from auraeve.agent.tools.message import MessageTool
from auraeve.bus.events import OutboundMessage


def test_message_tool_prefers_image_url_over_file_path() -> None:
    captured: list[OutboundMessage] = []

    async def _sender(msg: OutboundMessage) -> None:
        captured.append(msg)

    tool = MessageTool(send_callback=_sender)
    tool.set_context("napcat", "private:1")
    result = asyncio.run(
        tool.execute(
            content="",
            file_path="/tmp/local.png",
            image_url="https://example.com/photo.png",
        )
    )

    assert len(captured) == 1
    assert captured[0].image_url == "https://example.com/photo.png"
    assert captured[0].file_path is None
    assert "已优先使用 image_url" in result


def test_message_tool_keeps_file_path_when_no_http_image_url() -> None:
    captured: list[OutboundMessage] = []

    async def _sender(msg: OutboundMessage) -> None:
        captured.append(msg)

    tool = MessageTool(send_callback=_sender)
    tool.set_context("napcat", "private:1")
    asyncio.run(
        tool.execute(
            content="",
            file_path="/tmp/local.png",
            image_url="",
        )
    )

    assert len(captured) == 1
    assert captured[0].file_path == "/tmp/local.png"
