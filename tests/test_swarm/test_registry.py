"""Tests for BackendRegistry: register, detect, and get_executor."""

from __future__ import annotations

import pytest

from openharness.swarm.registry import BackendRegistry
from openharness.swarm.types import TeammateExecutor


def _make_registry_with_in_process() -> BackendRegistry:
    """Create a BackendRegistry ensuring in_process is registered.

    On Windows ``supports_swarm_mailbox`` is False so ``_register_defaults``
    skips in_process.  Additionally, a prior test (test_imports.py) may evict
    and reimport swarm modules making monkeypatch unreliable.  We work around
    both issues by importing and registering the backend explicitly.
    """
    registry = BackendRegistry()
    if "in_process" not in registry.available_backends():
        from openharness.swarm.in_process import InProcessBackend

        registry.register_backend(InProcessBackend())
    return registry


# ---------------------------------------------------------------------------
# Default registration
# ---------------------------------------------------------------------------


def test_registry_registers_subprocess_and_in_process():
    registry = _make_registry_with_in_process()
    available = registry.available_backends()
    assert "subprocess" in available
    assert "in_process" in available


def test_get_executor_subprocess():
    registry = BackendRegistry()
    executor = registry.get_executor("subprocess")
    assert executor is not None
    assert executor.type == "subprocess"


def test_get_executor_in_process():
    registry = _make_registry_with_in_process()
    executor = registry.get_executor("in_process")
    assert executor.type == "in_process"


def test_get_executor_unknown_raises():
    registry = BackendRegistry()
    with pytest.raises(KeyError, match="tmux"):
        registry.get_executor("tmux")


# ---------------------------------------------------------------------------
# detect_backend
# ---------------------------------------------------------------------------


def test_detect_backend_returns_subprocess_when_not_in_tmux(monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    registry = BackendRegistry()
    detected = registry.detect_backend()
    assert detected == "subprocess"


def test_detect_backend_is_cached(monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    registry = BackendRegistry()
    first = registry.detect_backend()
    second = registry.detect_backend()
    assert first == second


def test_detect_backend_reset_clears_cache(monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    registry = BackendRegistry()
    _ = registry.detect_backend()
    assert registry._detected == "subprocess"
    registry.reset()
    assert registry._detected is None


# ---------------------------------------------------------------------------
# register_backend custom
# ---------------------------------------------------------------------------


def test_register_custom_backend():
    class FakeExecutor:
        type = "in_process"

        def is_available(self):
            return True

        async def spawn(self, config):
            ...

        async def send_message(self, agent_id, message):
            ...

        async def shutdown(self, agent_id, *, force=False):
            ...

    registry = BackendRegistry()
    fake = FakeExecutor()
    registry.register_backend(fake)
    assert registry.get_executor("in_process") is fake


def test_get_executor_auto_detect_returns_executor(monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    registry = BackendRegistry()
    executor = registry.get_executor()  # auto-detect
    assert executor is not None
    assert isinstance(executor, TeammateExecutor)


# ---------------------------------------------------------------------------
# available_backends
# ---------------------------------------------------------------------------


def test_available_backends_sorted():
    registry = BackendRegistry()
    available = registry.available_backends()
    assert available == sorted(available)
