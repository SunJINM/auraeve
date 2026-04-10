from __future__ import annotations

import pytest

from auraeve.agent.tools.web import WebSearchTool


@pytest.mark.asyncio
async def test_web_search_prefers_tavily(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    tool = WebSearchTool(tavily_api_key="tvly-test", brave_api_key="brave-test")

    async def _fake_tavily(query: str, n: int) -> str:
        assert query == "latest ai news"
        assert n == 3
        return "tavily-result"

    async def _unexpected_brave(query: str, n: int) -> str:
        raise AssertionError("brave should not be used when Tavily key exists")

    async def _unexpected_ddg(query: str, n: int) -> str:
        raise AssertionError("duckduckgo should not be used when Tavily key exists")

    monkeypatch.setattr(tool, "_tavily_search", _fake_tavily)
    monkeypatch.setattr(tool, "_brave_search", _unexpected_brave)
    monkeypatch.setattr(tool, "_duckduckgo_search", _unexpected_ddg)

    result = await tool.execute(query="latest ai news", count=3)

    assert 'source="web_search"' in result
    assert "tavily-result" in result


@pytest.mark.asyncio
async def test_web_search_falls_back_to_brave_then_ddg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    brave_tool = WebSearchTool(tavily_api_key="", brave_api_key="brave-test")

    async def _fake_brave(query: str, n: int) -> str:
        return "brave-result"

    async def _unexpected_ddg(query: str, n: int) -> str:
        raise AssertionError("duckduckgo should not be used when Brave key exists")

    monkeypatch.setattr(brave_tool, "_brave_search", _fake_brave)
    monkeypatch.setattr(brave_tool, "_duckduckgo_search", _unexpected_ddg)

    brave_result = await brave_tool.execute(query="python", count=2)
    assert "brave-result" in brave_result

    ddg_tool = WebSearchTool(tavily_api_key="", brave_api_key="")

    async def _fake_ddg(query: str, n: int) -> str:
        return "ddg-result"

    monkeypatch.setattr(ddg_tool, "_duckduckgo_search", _fake_ddg)

    ddg_result = await ddg_tool.execute(query="python", count=2)
    assert "ddg-result" in ddg_result


@pytest.mark.asyncio
async def test_tavily_search_formats_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    tool = WebSearchTool(tavily_api_key="tvly-test")

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "results": [
                    {
                        "title": "Doc 1",
                        "url": "https://example.com/1",
                        "content": "summary 1",
                    },
                    {
                        "title": "Doc 2",
                        "url": "https://example.com/2",
                        "content": "summary 2",
                    },
                ]
            }

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict) -> _FakeResponse:
            assert url == "https://api.tavily.com/search"
            assert json["api_key"] == "tvly-test"
            assert json["query"] == "claude code"
            assert json["max_results"] == 2
            return _FakeResponse()

    monkeypatch.setattr("auraeve.agent.tools.web.httpx.AsyncClient", _FakeClient)

    result = await tool._tavily_search("claude code", 2)

    assert result.startswith("Tavily 搜索：claude code")
    assert "1. Doc 1" in result
    assert "https://example.com/1" in result
    assert "summary 2" in result
