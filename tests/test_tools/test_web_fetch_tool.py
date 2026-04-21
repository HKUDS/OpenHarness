"""Tests for web fetch and search tools."""

from __future__ import annotations

import time

import httpx
import pytest

from openharness.tools.base import ToolExecutionContext
from openharness.tools.web_fetch_tool import WebFetchTool, WebFetchToolInput, _html_to_text
from openharness.tools.web_search_tool import WebSearchTool, WebSearchToolInput


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
