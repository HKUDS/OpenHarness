"""Minimal bridge session spawner."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

from openharness.utils.shell import create_shell_subprocess


@dataclass
class SessionHandle:
    """Handle for a spawned bridge session."""

    session_id: str
    process: asyncio.subprocess.Process
    cwd: Path
    started_at: float = field(default_factory=time.time)

    async def kill(self) -> None:
        """Terminate the session process."""
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=3)
        except asyncio.TimeoutError:
            self.process.kill()
            await self.process.wait()


async def spawn_session(
    *,
    session_id: str,
    command: str,
    cwd: str | Path,
) -> SessionHandle:
    """Spawn a bridge-managed child session."""
    resolved_cwd = Path(cwd).resolve()
    process = await create_shell_subprocess(
        command,
        cwd=resolved_cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    return SessionHandle(session_id=session_id, process=process, cwd=resolved_cwd)
