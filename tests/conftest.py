"""Shared test fixtures."""

from __future__ import annotations

import pytest
import pytest_asyncio

from openharness.tasks.manager import shutdown_task_manager


@pytest.fixture(autouse=True)
def _scrub_anthropic_env(monkeypatch):
    """Keep real Claude Code/relay env vars out of the test suite.

    Settings resolution reads ANTHROPIC_AUTH_TOKEN (resolve_auth),
    ANTHROPIC_BASE_URL (third-party endpoint check), and ANTHROPIC_MODEL
    (provider env overrides), so contributors running Claude Code through a
    relay otherwise see auth and model assertions shadowed by their own
    environment. Tests that exercise these vars set them via monkeypatch,
    which runs after this fixture.
    """
    for name in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL"):
        monkeypatch.delenv(name, raising=False)


@pytest_asyncio.fixture(autouse=True)
async def _reset_background_task_manager():
    yield
    await shutdown_task_manager()
