"""Shell command execution tool."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class BashToolInput(BaseModel):
    """Arguments for the bash tool."""

    command: str = Field(description="Shell command to execute")
    cwd: str | None = Field(default=None, description="Working directory override")
    timeout_seconds: int = Field(default=120, ge=1, le=600)


def _shell_exec_args(command: str) -> tuple[str, ...]:
    """Return argv for asyncio.create_subprocess_exec (bash-like when possible)."""
    if os.name == "nt":
        bash = shutil.which("bash")
        if bash:
            return (bash, "-lc", command)
        ps = shutil.which("powershell.exe") or shutil.which("powershell")
        if ps:
            return (
                ps,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            )
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        return (comspec, "/c", command)
    return ("/bin/bash", "-lc", command)


class BashTool(BaseTool):
    """Execute a shell command with stdout/stderr capture."""

    name = "bash"
    description = "Run a shell command in the local repository."
    input_model = BashToolInput

    async def execute(self, arguments: BashToolInput, context: ToolExecutionContext) -> ToolResult:
        cwd = Path(arguments.cwd).expanduser() if arguments.cwd else context.cwd
        argv = _shell_exec_args(arguments.command)
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=arguments.timeout_seconds,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return ToolResult(
                output=f"Command timed out after {arguments.timeout_seconds} seconds",
                is_error=True,
            )

        parts = []
        if stdout:
            parts.append(stdout.decode("utf-8", errors="replace").rstrip())
        if stderr:
            parts.append(stderr.decode("utf-8", errors="replace").rstrip())

        text = "\n".join(part for part in parts if part).strip()
        if not text:
            text = "(no output)"

        if len(text) > 12000:
            text = f"{text[:12000]}\n...[truncated]..."

        return ToolResult(
            output=text,
            is_error=process.returncode != 0,
            metadata={"returncode": process.returncode},
        )
