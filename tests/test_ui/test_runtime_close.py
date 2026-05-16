"""Tests for runtime shutdown behavior."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from openharness.hooks import HookEvent
from openharness.ui.runtime import close_runtime


class _FakeManager:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeHookExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[object, dict]] = []

    async def execute(self, event, payload) -> None:
        self.calls.append((event, payload))


@pytest.mark.asyncio
async def test_close_runtime_logs_personalization_failures(tmp_path, monkeypatch, caplog):
    async def _noop_stop() -> None:
        return None

    def _boom(*args, **kwargs):
        raise RuntimeError("session sync failed")

    monkeypatch.setattr("openharness.sandbox.session.stop_docker_sandbox", _noop_stop)
    monkeypatch.setattr("openharness.personalization.session_hook.update_rules_from_session", _boom)

    manager = _FakeManager()
    hook_executor = _FakeHookExecutor()
    bundle = SimpleNamespace(
        current_settings=lambda: SimpleNamespace(
            memory=SimpleNamespace(session_fact_sync_enabled=True, auto_write_enabled=True)
        ),
        engine=SimpleNamespace(messages=[]),
        cwd=str(tmp_path),
        mcp_manager=manager,
        hook_executor=hook_executor,
    )

    with caplog.at_level(logging.ERROR):
        await close_runtime(bundle)

    assert manager.closed is True
    assert any(event == HookEvent.SESSION_END for event, _ in hook_executor.calls)
    assert "Session-end personalization sync failed" in caplog.text