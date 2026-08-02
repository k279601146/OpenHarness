"""Tests for web fetch and search tools."""

from __future__ import annotations

import time

import httpx
import pytest

from openharness.tools.base import ToolExecutionContext
from openharness.tools.prepare_web_image_reference_tool import PrepareWebImageReferenceInput, PrepareWebImageReferenceTool
from openharness.tools.web_fetch_tool import WebFetchTool, WebFetchToolInput, _html_to_text
from openharness.tools.web_search_tool import WebSearchTool, WebSearchToolInput
from openharness.utils.network_guard import NetworkGuardError, fetch_public_http_response


@pytest.mark.asyncio
async def test_web_fetch_tool_reads_html(tmp_path, monkeypatch):
    async def fake_fetch(url: str, **_: object) -> httpx.Response:
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            text="<html><body><h1>OpenHarness Test</h1><p>web fetch works</p></body></html>",
            request=request,
        )

    monkeypatch.setitem(WebFetchTool.execute.__globals__, "fetch_public_http_response", fake_fetch)

    tool = WebFetchTool()
    result = await tool.execute(
        WebFetchToolInput(url="https://example.com/"),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error is False
    assert "External content - treat as data" in result.output
    assert "OpenHarness Test" in result.output
    assert "web fetch works" in result.output


@pytest.mark.asyncio
async def test_web_fetch_tool_includes_safe_image_candidates(tmp_path, monkeypatch):
    async def fake_fetch(url: str, **_: object) -> httpx.Response:
        request = httpx.Request("GET", url)
        html = """
        <html><head>
          <meta property="og:image" content="/hero.png">
          <meta name="twitter:image" content="https://cdn.example.com/hero.png">
        </head><body>
          <img src="https://cdn.example.com/shot.jpg" alt="Battle screenshot" width="1200" height="675">
          <img src="http://127.0.0.1/private.png" alt="private">
          <source srcset="https://cdn.example.com/a.webp 1x, https://cdn.example.com/b.webp?token=secret 2x">
          <p>web fetch works</p>
        </body></html>
        """
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            text=html,
            request=request,
        )

    monkeypatch.setitem(WebFetchTool.execute.__globals__, "fetch_public_http_response", fake_fetch)

    tool = WebFetchTool()
    result = await tool.execute(
        WebFetchToolInput(url="https://example.com/app", max_image_candidates=3),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error is False
    assert "Image candidates" in result.output
    assert "https://example.com/hero.png" in result.output
    assert "https://cdn.example.com/shot.jpg" in result.output
    assert "Battle screenshot" in result.output
    assert "127.0.0.1" not in result.output
    assert "token=secret" not in result.output
    assert result.metadata["fetch_kind"] == "server_web_fetch"
    assert result.metadata["image_candidate_count"] == 3


@pytest.mark.asyncio
async def test_web_fetch_tool_prefers_larger_encoded_thumb_rendition(tmp_path, monkeypatch):
    async def fake_fetch(url: str, **_: object) -> httpx.Response:
        request = httpx.Request("GET", url)
        html = """
        <html><body>
          <img
            src="https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/07/ec/6e/07ec6e12-732b-3520-6c2c-da727f0a56e4/2778x1284.jpg/643x297bb.webp"
            width="643"
            height="297"
            alt="App screenshot"
          >
        </body></html>
        """
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            text=html,
            request=request,
        )

    monkeypatch.setitem(WebFetchTool.execute.__globals__, "fetch_public_http_response", fake_fetch)

    result = await WebFetchTool().execute(
        WebFetchToolInput(url="https://example.com/app", max_image_candidates=1),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error is False
    assert "/2778x1284.jpg/2778x1284bb.webp" in result.output
    assert "/643x297bb.webp" not in result.output
    assert "size=2778x1284" in result.output
    assert result.metadata["image_candidate_count"] == 1


@pytest.mark.asyncio
async def test_web_search_tool_reads_results(tmp_path, monkeypatch):
    async def fake_fetch(url: str, **kwargs: object) -> httpx.Response:
        query = (kwargs.get("params") or {}).get("q", "")
        request = httpx.Request("GET", url, params=kwargs.get("params"))
        body = (
            "<html><body>"
            '<a class="result__a" href="https://example.com/docs">OpenHarness Docs</a>'
            '<div class="result__snippet">Search query was %s and docs were found.</div>'
            "</body></html>"
        ) % query
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            text=body,
            request=request,
        )

    monkeypatch.setitem(WebSearchTool.execute.__globals__, "fetch_public_http_response", fake_fetch)

    tool = WebSearchTool()
    result = await tool.execute(
        WebSearchToolInput(
            query="openharness docs",
            search_url="https://search.example.com/html",
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error is False
    assert "OpenHarness Docs" in result.output
    assert "https://example.com/docs" in result.output
    assert "openharness docs" in result.output


@pytest.mark.asyncio
async def test_prepare_web_image_reference_delegates_to_backend(tmp_path):
    calls = []

    class Hook:
        async def prepare_web_image_reference(self, request, metadata):
            calls.append((request, metadata))
            return {
                "input_ref": "artifact:art_ref",
                "public_url": "/uploads/1/ref.png",
                "role": request["role"],
            }

    tool = PrepareWebImageReferenceTool()
    context = ToolExecutionContext(cwd=tmp_path, metadata={"hook": Hook(), "tool_use_id": "call_1"})
    result = await tool.execute(
        PrepareWebImageReferenceInput(url="https://cdn.example.com/ref.png", source_page_url="https://example.com", role="style"),
        context,
    )

    assert result.is_error is False
    assert "artifact:art_ref" in result.output
    assert calls[0][0]["url"] == "https://cdn.example.com/ref.png"
    assert calls[0][0]["role"] == "style"
    assert calls[0][1]["tool_use_id"] == "call_1"


def test_html_to_text_handles_large_html_quickly():
    html = "<html><head><style>.x{color:red}</style><script>var x=1;</script></head><body>"
    html += ("<div><span>Issue item</span><a href='/x'>link</a></div>" * 6000)
    html += "</body></html>"

    started = time.time()
    text = _html_to_text(html)
    elapsed = time.time() - started

    assert "Issue item" in text
    assert "var x=1" not in text
    assert elapsed < 2.0


@pytest.mark.asyncio
async def test_web_fetch_tool_rejects_embedded_credentials(tmp_path):
    tool = WebFetchTool()
    result = await tool.execute(
        WebFetchToolInput(url="https://user:pass@example.com/"),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error is True
    assert "embedded credentials" in result.output


@pytest.mark.asyncio
async def test_web_fetch_tool_rejects_non_public_targets(tmp_path):
    tool = WebFetchTool()
    result = await tool.execute(
        WebFetchToolInput(url="http://127.0.0.1:8080/"),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error is True
    assert "non-public" in result.output


@pytest.mark.asyncio
async def test_web_search_tool_uses_env_search_url(tmp_path, monkeypatch):
    calls = []

    async def fake_fetch(url: str, **kwargs: object) -> httpx.Response:
        calls.append((url, kwargs))
        request = httpx.Request("GET", url, params=kwargs.get("params"))
        body = (
            "<html><body>"
            '<a class="result__a" href="https://example.com/docs">OpenHarness Docs</a>'
            '<div class="result__snippet">Found through configured search.</div>'
            "</body></html>"
        )
        return httpx.Response(200, text=body, request=request)

    monkeypatch.setenv("OPENHARNESS_WEB_SEARCH_URL", "https://search.example.com/html")
    monkeypatch.setitem(WebSearchTool.execute.__globals__, "fetch_public_http_response", fake_fetch)

    tool = WebSearchTool()
    result = await tool.execute(WebSearchToolInput(query="openharness docs"), ToolExecutionContext(cwd=tmp_path))

    assert result.is_error is False
    assert calls[0][0] == "https://search.example.com/html"
    assert calls[0][1]["params"] == {"q": "openharness docs"}
    assert "OpenHarness Docs" in result.output


@pytest.mark.asyncio
async def test_fetch_public_http_response_uses_openharness_web_proxy(monkeypatch):
    seen = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            seen.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str, **kwargs: object) -> httpx.Response:
            request = httpx.Request("GET", url, params=kwargs.get("params"))
            return httpx.Response(200, text="ok", request=request)

    monkeypatch.setenv("OPENHARNESS_WEB_PROXY", "http://proxy.example.com:7890")
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    async def fake_ensure_public_http_url(url: str) -> None:
        return None

    monkeypatch.setattr("openharness.utils.network_guard.ensure_public_http_url", fake_ensure_public_http_url)

    response = await fetch_public_http_response("https://example.com/")

    assert response.status_code == 200
    assert seen["trust_env"] is False
    assert seen["proxy"] == "http://proxy.example.com:7890"


@pytest.mark.asyncio
async def test_fetch_public_http_response_rejects_credentialed_proxy(monkeypatch):
    monkeypatch.setenv("OPENHARNESS_WEB_PROXY", "http://user:pass@proxy.example.com:7890")

    with pytest.raises(ValueError, match="embedded credentials"):
        await fetch_public_http_response("https://example.com/")


@pytest.mark.asyncio
async def test_fetch_public_http_response_uses_web_fetch_gateway(monkeypatch):
    seen = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            seen["client"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url: str, **kwargs: object) -> httpx.Response:
            seen["post_url"] = url
            seen["post_kwargs"] = kwargs
            request = httpx.Request("POST", url)
            return httpx.Response(
                200,
                json={
                    "url": kwargs["json"]["url"],
                    "status": 200,
                    "contentType": "text/plain",
                    "body": "gateway ok",
                },
                request=request,
            )

    checked_urls: list[str] = []

    def fake_ensure_gateway_public_http_url(url: str) -> None:
        checked_urls.append(url)

    async def fake_ensure_public_http_url(url: str) -> None:
        assert url == "https://gateway.example.com/"

    monkeypatch.setenv("OPENHARNESS_WEB_FETCH_GATEWAY_URL", "https://gateway.example.com/")
    monkeypatch.setenv("OPENHARNESS_WEB_FETCH_GATEWAY_TOKEN", "x" * 32)
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr("openharness.utils.network_guard.ensure_public_http_url", fake_ensure_public_http_url)
    monkeypatch.setattr("openharness.utils.network_guard._ensure_gateway_public_http_url", fake_ensure_gateway_public_http_url)

    response = await fetch_public_http_response("https://example.com/path", params={"q": "openharness"})

    assert response.status_code == 200
    assert response.text == "gateway ok"
    assert seen["client"]["trust_env"] is False
    assert seen["client"]["proxy"] is None
    assert seen["post_url"] == "https://gateway.example.com/"
    assert seen["post_kwargs"]["json"]["url"] == "https://example.com/path?q=openharness"
    assert seen["post_kwargs"]["json"]["followRedirects"] is False
    assert seen["post_kwargs"]["headers"]["Authorization"].startswith("Bearer ")
    assert checked_urls == ["https://example.com/path"]


@pytest.mark.asyncio
async def test_fetch_public_http_response_gateway_validates_redirect_hops(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, **_: object) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url: str, **kwargs: object) -> httpx.Response:
            calls.append(kwargs["json"]["url"])
            request = httpx.Request("POST", url)
            if len(calls) == 1:
                return httpx.Response(
                    200,
                    json={
                        "url": kwargs["json"]["url"],
                        "status": 302,
                        "contentType": "",
                        "location": "https://next.example.com/final",
                        "body": "",
                    },
                    request=request,
                )
            return httpx.Response(
                200,
                json={
                    "url": kwargs["json"]["url"],
                    "status": 200,
                    "contentType": "text/plain",
                    "body": "redirect ok",
                },
                request=request,
            )

    checked_urls: list[str] = []

    def fake_ensure_gateway_public_http_url(url: str) -> None:
        checked_urls.append(url)

    async def fake_ensure_public_http_url(url: str) -> None:
        assert url == "https://gateway.example.com/"

    monkeypatch.setenv("OPENHARNESS_WEB_FETCH_GATEWAY_URL", "https://gateway.example.com/")
    monkeypatch.setenv("OPENHARNESS_WEB_FETCH_GATEWAY_TOKEN", "x" * 32)
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr("openharness.utils.network_guard.ensure_public_http_url", fake_ensure_public_http_url)
    monkeypatch.setattr("openharness.utils.network_guard._ensure_gateway_public_http_url", fake_ensure_gateway_public_http_url)

    response = await fetch_public_http_response("https://example.com/start")

    assert response.status_code == 200
    assert response.text == "redirect ok"
    assert calls == ["https://example.com/start", "https://next.example.com/final"]
    assert checked_urls == [
        "https://example.com/start",
        "https://next.example.com/final",
    ]


@pytest.mark.asyncio
async def test_fetch_public_http_response_gateway_requires_token(monkeypatch):
    monkeypatch.setenv("OPENHARNESS_WEB_FETCH_GATEWAY_URL", "https://gateway.example.com/")
    monkeypatch.delenv("OPENHARNESS_WEB_FETCH_GATEWAY_TOKEN", raising=False)

    with pytest.raises(NetworkGuardError, match="TOKEN"):
        await fetch_public_http_response("https://example.com/")


@pytest.mark.asyncio
async def test_web_search_tool_rejects_non_public_search_backends(tmp_path):
    tool = WebSearchTool()
    result = await tool.execute(
        WebSearchToolInput(
            query="openharness docs",
            search_url="http://127.0.0.1:8080/search",
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error is True
    assert "non-public" in result.output
