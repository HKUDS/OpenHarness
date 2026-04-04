"""Tests for the React terminal launcher path."""

from __future__ import annotations

import pytest

from openharness.ui.app import run_repl
from openharness.ui.react_launcher import build_backend_command


def test_build_backend_command_includes_flags():
    command = build_backend_command(
        cwd="/tmp/demo",
        model="kimi-k2.5",
        base_url="https://api.moonshot.cn/anthropic",
        system_prompt="system",
        api_key="secret",
        api_format="openai",
    )
    assert command[:3] == [command[0], "-m", "openharness"]
    assert "--backend-only" in command
    assert "--cwd" in command
    assert "--model" in command
    assert "--base-url" in command
    assert "--system-prompt" in command
    assert "--api-key" in command
    assert "--api-format" in command


@pytest.mark.asyncio
async def test_run_repl_uses_react_launcher_by_default(monkeypatch):
    seen = {}

    async def _launch(**kwargs):
        seen.update(kwargs)
        return 0

    monkeypatch.setattr("openharness.ui.app.launch_react_tui", _launch)
    await run_repl(prompt="hi", cwd="/tmp/demo", model="kimi-k2.5", api_format="openai")

    assert seen["prompt"] == "hi"
    assert seen["cwd"] == "/tmp/demo"
    assert seen["model"] == "kimi-k2.5"
    assert seen["api_format"] == "openai"
