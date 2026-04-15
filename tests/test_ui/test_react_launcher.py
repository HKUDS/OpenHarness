"""Tests for the React terminal launcher path."""

from __future__ import annotations

import pytest
from types import SimpleNamespace

from openharness.ui.app import run_print_mode, run_repl
from openharness.ui.react_launcher import build_backend_command


class _AsyncIterator:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


def test_build_backend_command_includes_flags():
    command = build_backend_command(
        cwd="/tmp/demo",
        model="kimi-k2.5",
        base_url="https://api.moonshot.cn/anthropic",
        system_prompt="system",
        api_key="secret",
    )
    assert command[:3] == [command[0], "-m", "openharness"]
    assert "--backend-only" in command
    assert "--cwd" in command
    assert "--model" in command
    assert "--base-url" in command
    assert "--system-prompt" in command
    assert "--api-key" in command


@pytest.mark.asyncio
async def test_run_repl_uses_react_launcher_by_default(monkeypatch):
    seen = {}

    async def _launch(**kwargs):
        seen.update(kwargs)
        return 0

    monkeypatch.setattr("openharness.ui.app.launch_react_tui", _launch)
    await run_repl(prompt="hi", cwd="/tmp/demo", model="kimi-k2.5")

    assert seen["prompt"] == "hi"
    assert seen["cwd"] == "/tmp/demo"
    assert seen["model"] == "kimi-k2.5"


@pytest.mark.asyncio
async def test_run_print_mode_passes_cwd_to_build_runtime(monkeypatch):
    seen = {}

    async def _build_runtime(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            app_state=SimpleNamespace(get=lambda: None),
            mcp_manager=SimpleNamespace(list_statuses=lambda: []),
            commands=SimpleNamespace(list_commands=lambda: []),
            events=_AsyncIterator(),
        )

    async def _start_runtime(_bundle):
        return None

    async def _handle_line(*_args, **_kwargs):
        return None

    async def _close_runtime(_bundle):
        return None

    monkeypatch.setattr("openharness.ui.app.build_runtime", _build_runtime)
    monkeypatch.setattr("openharness.ui.app.start_runtime", _start_runtime)
    monkeypatch.setattr("openharness.ui.app.handle_line", _handle_line)
    monkeypatch.setattr("openharness.ui.app.close_runtime", _close_runtime)

    await run_print_mode(prompt="hi", cwd="/tmp/demo")

    assert seen["cwd"] == "/tmp/demo"
