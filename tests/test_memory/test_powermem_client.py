"""Tests for PowerMem HTTP client helpers."""

from __future__ import annotations

from unittest.mock import patch

from openharness.config.settings import MemorySettings
from openharness.memory.powermem_client import (
    _normalize_http_results,
    search_powermem_http,
    search_powermem_for_prompt,
)


def test_normalize_http_results_success():
    payload = {
        "success": True,
        "data": {
            "results": [
                {"memory_id": 42, "content": "User likes tea"},
            ]
        },
    }
    pairs = _normalize_http_results(payload)
    assert pairs == [("powermem-42", "User likes tea")]


def test_normalize_http_results_empty():
    assert _normalize_http_results({}) == []
    assert _normalize_http_results({"success": False}) == []


def test_search_powermem_http_calls_api():
    memory = MemorySettings(
        backend="powermem_http",
        powermem_base_url="http://127.0.0.1:8000/",
        powermem_api_key="secret",
        powermem_user_id="u1",
        max_files=3,
    )

    class FakeResp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "success": True,
                "data": {"results": [{"memory_id": 1, "content": "fact"}]},
            }

    with patch("openharness.memory.powermem_client.httpx.post", return_value=FakeResp()) as m:
        out = search_powermem_http("hello", memory)

    assert out == [("powermem-1", "fact")]
    m.assert_called_once()
    _args, kwargs = m.call_args
    assert kwargs["json"]["query"] == "hello"
    assert kwargs["json"]["limit"] == 3
    assert kwargs["json"]["user_id"] == "u1"
    assert kwargs["headers"]["X-API-Key"] == "secret"
    assert _args[0] == "http://127.0.0.1:8000/api/v1/memories/search"


def test_search_powermem_for_prompt_dispatches():
    memory = MemorySettings(backend="local")
    assert search_powermem_for_prompt("q", memory) == []
