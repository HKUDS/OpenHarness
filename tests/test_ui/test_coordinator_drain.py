"""Tests for the coordinator-mode async-agent drain helper and its integration
into the interactive UI hosts (React backend and Textual app).
"""

from __future__ import annotations

import pytest

from openharness.ui import coordinator_drain
from openharness.ui.backend_host import BackendHostConfig, ReactBackendHost
from openharness.ui.coordinator_drain import (
    drain_coordinator_async_agents,
    pending_async_agent_entries,
)
from openharness.ui.runtime import build_runtime, close_runtime, start_runtime

from .test_react_backend import StaticApiClient


def test_pending_async_agent_entries_skips_notified_and_missing_id():
    metadata = {
        "async_agent_tasks": [
            {"task_id": "t1", "agent_id": "a1"},
            {"task_id": "t2", "agent_id": "a2", "notification_sent": True},
            {"task_id": "", "agent_id": "a3"},
            "not-a-dict",
        ]
    }
    pending = pending_async_agent_entries(metadata)
    assert [entry["task_id"] for entry in pending] == ["t1"]


def test_pending_async_agent_entries_handles_missing_metadata():
    assert pending_async_agent_entries(None) == []
    assert pending_async_agent_entries({}) == []
    assert pending_async_agent_entries({"async_agent_tasks": "not a list"}) == []


@pytest.mark.asyncio
async def test_drain_returns_immediately_when_no_pending_entries():
    """No pending entries = no follow-up turn, no `Waiting for...` message."""

    class _FakeEngine:
        tool_metadata: dict[str, object] = {}

    class _FakeBundle:
        engine = _FakeEngine()

    announcements: list[str] = []

    async def _print(message: str) -> None:
        announcements.append(message)

    async def _render(_event):  # pragma: no cover - never called in this scenario
        raise AssertionError("render_event must not be invoked when no work is pending")

    await drain_coordinator_async_agents(
        _FakeBundle(),
        prompt_seed="hi",
        print_system=_print,
        render_event=_render,
    )
    assert announcements == []


@pytest.mark.asyncio
async def test_drain_returns_when_bundle_has_no_engine():
    class _NoEngineBundle:
        pass

    async def _print(_message: str) -> None:  # pragma: no cover
        raise AssertionError("print_system must not be invoked")

    async def _render(_event):  # pragma: no cover
        raise AssertionError("render_event must not be invoked")

    await drain_coordinator_async_agents(
        _NoEngineBundle(),
        prompt_seed="hi",
        print_system=_print,
        render_event=_render,
    )


@pytest.mark.asyncio
async def test_react_backend_drains_async_agents_in_coordinator_mode(tmp_path, monkeypatch):
    """Regression: React TUI's `_process_line` must invoke the coordinator drain.

    Without this, `<task-notification>` envelopes never reach the coordinator
    after a worker finishes, so either the user is left holding stale state or
    the coordinator polls in-turn (locking the UI).
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("unused")))
    host._bundle = await build_runtime(api_client=StaticApiClient("unused"))

    async def _fake_handle_line(bundle, line, print_system, render_event, clear_output):
        del bundle, line, print_system, render_event, clear_output
        return True

    monkeypatch.setattr("openharness.ui.backend_host.handle_line", _fake_handle_line)
    monkeypatch.setattr("openharness.ui.backend_host.is_coordinator_mode", lambda: True)

    drain_calls: list[dict[str, object]] = []

    async def _fake_drain(bundle, *, prompt_seed, print_system, render_event):
        drain_calls.append(
            {
                "bundle_is_host_bundle": bundle is host._bundle,
                "prompt_seed": prompt_seed,
            }
        )

    monkeypatch.setattr(
        "openharness.ui.backend_host.drain_coordinator_async_agents",
        _fake_drain,
    )

    async def _emit(_event):
        return None

    host._emit = _emit  # type: ignore[method-assign]
    await start_runtime(host._bundle)
    try:
        should_continue = await host._process_line("dispatch a worker")
    finally:
        await close_runtime(host._bundle)

    assert should_continue is True
    assert drain_calls == [{"bundle_is_host_bundle": True, "prompt_seed": "dispatch a worker"}]


@pytest.mark.asyncio
async def test_react_backend_skips_drain_when_not_coordinator(tmp_path, monkeypatch):
    """When coordinator mode is off, the drain must not run — it would needlessly
    poll the task manager and submit follow-up turns for unrelated background tasks.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("unused")))
    host._bundle = await build_runtime(api_client=StaticApiClient("unused"))

    async def _fake_handle_line(bundle, line, print_system, render_event, clear_output):
        del bundle, line, print_system, render_event, clear_output
        return True

    monkeypatch.setattr("openharness.ui.backend_host.handle_line", _fake_handle_line)
    monkeypatch.setattr("openharness.ui.backend_host.is_coordinator_mode", lambda: False)

    async def _fake_drain(*args, **kwargs):  # pragma: no cover
        del args, kwargs
        raise AssertionError("drain must not be called outside coordinator mode")

    monkeypatch.setattr(
        "openharness.ui.backend_host.drain_coordinator_async_agents",
        _fake_drain,
    )

    async def _emit(_event):
        return None

    host._emit = _emit  # type: ignore[method-assign]
    await start_runtime(host._bundle)
    try:
        should_continue = await host._process_line("hi")
    finally:
        await close_runtime(host._bundle)

    assert should_continue is True


def test_drain_module_exposes_public_api():
    """The drain helpers must keep the public names other modules import."""
    assert callable(coordinator_drain.drain_coordinator_async_agents)
    assert callable(coordinator_drain.pending_async_agent_entries)
    assert callable(coordinator_drain.wait_for_completed_async_agent_entries)
    assert callable(coordinator_drain.format_completed_task_notifications)
    assert callable(coordinator_drain.submit_follow_up)
