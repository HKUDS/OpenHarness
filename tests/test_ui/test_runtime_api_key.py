"""Tests for build_runtime auth failure handling."""

from __future__ import annotations

import pytest

from openharness.ui.runtime import build_runtime


@pytest.mark.asyncio
async def test_build_runtime_exits_cleanly_when_auth_resolution_fails(monkeypatch):
    """build_runtime should raise SystemExit(1) — not ValueError — when auth resolution fails."""

    def fake_resolve_auth(self):
        raise ValueError("No credentials found")

    monkeypatch.setattr("openharness.config.settings.Settings.resolve_auth", fake_resolve_auth)

    with pytest.raises(SystemExit, match="1"):
        await build_runtime(active_profile="claude-api")


@pytest.mark.asyncio
async def test_build_runtime_exits_cleanly_for_openai_format(monkeypatch):
    """Same check for the openai-compatible path."""

    def fake_resolve_auth(self):
        raise ValueError("No credentials found")

    monkeypatch.setattr("openharness.config.settings.Settings.resolve_auth", fake_resolve_auth)

    with pytest.raises(SystemExit, match="1"):
        await build_runtime(active_profile="openai-compatible", api_format="openai")
