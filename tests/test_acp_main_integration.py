# tests/test_acp_main_integration.py
"""验证 ACPChannel 被正确注入 WebUIServer。"""
from unittest.mock import MagicMock, AsyncMock
from auraeve.transports.acp.channel import ACPChannel, ACPChannelConfig
from auraeve.webui.server import WebUIServer
from auraeve.services.session_service import SessionService


def test_webui_server_accepts_acp_channel() -> None:
    bus = MagicMock()
    bus.subscribe_outbound = MagicMock()
    bus.unsubscribe_outbound = MagicMock()
    bus.publish_inbound = AsyncMock()
    session_service = SessionService()
    acp_channel = ACPChannel(
        config=ACPChannelConfig(),
        bus=bus,
        session_service=session_service,
        token="t",
        agent_id="main",
        workspace_id="ws",
    )
    server = WebUIServer(
        chat_service=MagicMock(),
        config_service=MagicMock(),
        token="t",
        acp_channel=acp_channel,
    )
    # /acp 路由应已注册
    routes = [r.path for r in server._app.routes]
    assert "/acp" in routes


def test_webui_server_without_acp_channel_has_no_acp_route() -> None:
    server = WebUIServer(
        chat_service=MagicMock(),
        config_service=MagicMock(),
        token="t",
    )
    routes = [r.path for r in server._app.routes]
    assert "/acp" not in routes
