"""Anonymous Parallel Search MCP backend for the built-in web search tool."""

from __future__ import annotations

import json

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from openharness.config import load_settings
from openharness.utils.network_guard import (
    NetworkGuardError,
    ResolutionMode,
    ensure_http_url_allowed,
    get_web_resolution_mode,
    parse_synthetic_dns_cidrs,
    validate_http_url,
)

PARALLEL_MCP_URL = "https://search.parallel.ai/mcp"


async def search_parallel(query: str, limit: int, session_id: str) -> list[dict[str, str]]:
    """Search through the official MCP transport without ambient credentials."""
    web = load_settings().web
    if web.proxy:
        validate_http_url(web.proxy)
    mode = get_web_resolution_mode(web.proxy, configured_mode=web.resolution_mode)
    cidrs = (
        parse_synthetic_dns_cidrs(",".join(web.synthetic_dns_cidrs))
        if mode is ResolutionMode.SYNTHETIC_DNS
        else ()
    )
    await ensure_http_url_allowed(PARALLEL_MCP_URL, mode=mode, synthetic_cidrs=cidrs)
    async with (
        httpx.AsyncClient(
            headers={"User-Agent": "OpenHarness/0.1"},
            trust_env=False,
            follow_redirects=False,
            timeout=20.0,
            proxy=web.proxy,
        ) as client,
        streamable_http_client(PARALLEL_MCP_URL, http_client=client) as streams,
        ClientSession(streams[0], streams[1]) as session,
    ):
        await session.initialize()
        result = await session.call_tool(
            "web_search",
            {"objective": query, "search_queries": [query], "session_id": session_id},
        )
    texts = [item.text for item in result.content if item.type == "text"]
    if result.isError:
        raise ValueError("; ".join(texts) or "Parallel search returned an error")
    payload = result.structuredContent
    if payload is None:
        payload = json.loads("\n".join(texts))
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise TypeError("Parallel search returned an invalid results payload")
    results = []
    for item in payload["results"]:
        if not isinstance(item, dict) or not isinstance(item.get("url"), str):
            continue
        try:
            validate_http_url(item["url"])
        except NetworkGuardError:
            continue
        excerpts = item.get("excerpts") or []
        if not isinstance(excerpts, list) or any(not isinstance(text, str) for text in excerpts):
            raise ValueError("Parallel search returned invalid excerpts")
        results.append(
            {
                "title": str(item.get("title") or item["url"]),
                "url": item["url"],
                "snippet": "\n".join(excerpts)[:5000],
            }
        )
        if len(results) >= limit:
            break
    return results
