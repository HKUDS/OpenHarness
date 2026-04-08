"""PowerMem integration: retrieve memories for system prompt injection."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from openharness.config.settings import MemorySettings

logger = logging.getLogger(__name__)

_sdk_memory: object | None = None
_sdk_cache_key: str | None = None


def reset_powermem_sdk_cache() -> None:
    """Clear cached SDK client (for tests)."""
    global _sdk_memory, _sdk_cache_key
    _sdk_memory = None
    _sdk_cache_key = None


def _normalize_http_results(payload: object) -> list[tuple[str, str]]:
    if not isinstance(payload, dict):
        return []
    if not payload.get("success"):
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    raw_results = data.get("results")
    if not isinstance(raw_results, list):
        return []
    out: list[tuple[str, str]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        content = item.get("content") or item.get("memory") or ""
        if not isinstance(content, str):
            content = str(content)
        mid = item.get("memory_id", item.get("id", ""))
        label = f"powermem-{mid}" if mid != "" else "powermem"
        out.append((str(label), content.strip()))
    return out


def search_powermem_http(query: str, memory: MemorySettings) -> list[tuple[str, str]]:
    base = (memory.powermem_base_url or "").strip().rstrip("/")
    if not base:
        logger.warning("memory.backend is powermem_http but powermem_base_url is empty")
        return []

    url = f"{base}/api/v1/memories/search"
    body: dict[str, object] = {
        "query": query,
        "limit": max(1, min(100, memory.max_files)),
    }
    if memory.powermem_user_id:
        body["user_id"] = memory.powermem_user_id
    if memory.powermem_agent_id:
        body["agent_id"] = memory.powermem_agent_id
    if memory.powermem_run_id:
        body["run_id"] = memory.powermem_run_id

    headers: dict[str, str] = {}
    if (memory.powermem_api_key or "").strip():
        headers["X-API-Key"] = memory.powermem_api_key.strip()

    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=30.0)
        resp.raise_for_status()
        return _normalize_http_results(resp.json())
    except httpx.HTTPError as e:
        logger.warning("PowerMem HTTP search failed: %s", e)
        return []


def _get_sdk_memory(memory: MemorySettings) -> object | None:
    global _sdk_memory, _sdk_cache_key
    try:
        from powermem import create_memory
    except ImportError:
        logger.warning("memory.backend is powermem_sdk but powermem is not installed")
        return None

    key = f"{memory.powermem_agent_id or ''}|{memory.powermem_user_id or ''}"
    if _sdk_memory is not None and _sdk_cache_key == key:
        return _sdk_memory

    kwargs: dict[str, str] = {}
    if memory.powermem_agent_id:
        kwargs["agent_id"] = memory.powermem_agent_id
    _sdk_memory = create_memory(**kwargs)
    _sdk_cache_key = key
    return _sdk_memory


def search_powermem_sdk(query: str, memory: MemorySettings) -> list[tuple[str, str]]:
    client = _get_sdk_memory(memory)
    if client is None:
        return []

    try:
        raw = client.search(
            query,
            user_id=memory.powermem_user_id,
            agent_id=memory.powermem_agent_id,
            run_id=memory.powermem_run_id,
            limit=max(1, min(100, memory.max_files)),
        )
    except Exception as e:
        logger.warning("PowerMem SDK search failed: %s", e)
        return []

    if not isinstance(raw, dict):
        return []
    results = raw.get("results")
    if not isinstance(results, list):
        return []

    out: list[tuple[str, str]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        text = item.get("memory") or item.get("content") or ""
        if not isinstance(text, str):
            text = str(text)
        mid = item.get("id", item.get("memory_id", ""))
        label = f"powermem-{mid}" if mid != "" else "powermem"
        out.append((str(label), text.strip()))
    return out


def search_powermem_for_prompt(query: str, memory: MemorySettings) -> list[tuple[str, str]]:
    b = memory.backend
    if b == "powermem_http":
        return search_powermem_http(query, memory)
    if b == "powermem_sdk":
        return search_powermem_sdk(query, memory)
    return []
