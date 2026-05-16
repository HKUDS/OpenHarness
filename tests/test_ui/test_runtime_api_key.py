"""Tests for build_runtime behaviour when no API key is configured."""

from __future__ import annotations

import pytest

from openharness.ui.runtime import build_runtime


@pytest.mark.asyncio
async def test_build_runtime_exits_cleanly_when_api_key_missing(monkeypatch):
    """build_runtime should raise SystemExit(1) — not ValueError — when no API key is set."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(SystemExit, match="1"):
        await build_runtime()


@pytest.mark.asyncio
async def test_build_runtime_exits_cleanly_for_openai_format(monkeypatch):
    """Same check for the openai api_format path."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(SystemExit, match="1"):
        await build_runtime(api_format="openai")
