"""Module-level Docker sandbox session registry."""

from __future__ import annotations

import atexit
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openharness.config import Settings
    from openharness.sandbox.docker_backend import DockerSandboxSession

logger = logging.getLogger(__name__)

_active_session: DockerSandboxSession | None = None


def get_docker_sandbox():
    """Return the active Docker sandbox session, or ``None``."""
    return _active_session


def is_docker_sandbox_active() -> bool:
    """Return whether a Docker sandbox session is currently running."""
    return _active_session is not None and _active_session.is_running


async def start_docker_sandbox(
    settings: Settings,
    session_id: str,
    cwd: Path,
) -> None:
    """Start a Docker sandbox session for the current OpenHarness session."""
    global _active_session  # noqa: PLW0603

    from openharness.sandbox.docker_backend import DockerSandboxSession, get_docker_availability

    availability = get_docker_availability(settings)
    if not availability.available:
        if settings.sandbox.fail_if_unavailable:
            from openharness.sandbox.adapter import SandboxUnavailableError

            raise SandboxUnavailableError(
                availability.reason or "Docker sandbox is unavailable"
            )
        logger.warning("Docker sandbox unavailable: %s", availability.reason)
        return

    session = DockerSandboxSession(settings=settings, session_id=session_id, cwd=cwd)
    await session.start()
    _active_session = session

    # Safety net: stop the container if the process exits without close_runtime()
    atexit.register(session.stop_sync)


async def stop_docker_sandbox() -> None:
    """Stop the active Docker sandbox session, if any."""
    global _active_session  # noqa: PLW0603
    if _active_session is not None:
        await _active_session.stop()
        _active_session = None
