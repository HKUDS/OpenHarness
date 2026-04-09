"""Shell command execution tool."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

from openharness.sandbox import SandboxUnavailableError
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.utils.shell import create_shell_subprocess


class BashToolInput(BaseModel):
    """Arguments for the bash tool."""

    command: str = Field(description="Shell command to execute")
    cwd: str | None = Field(default=None, description="Working directory override")
    timeout_seconds: int = Field(default=120, ge=1, le=600)


class BashTool(BaseTool):
    """Execute a shell command with stdout/stderr capture."""

    name = "bash"
    description = "Run a shell command in the local repository."
    input_model = BashToolInput

    async def execute(self, arguments: BashToolInput, context: ToolExecutionContext) -> ToolResult:
        cwd = Path(arguments.cwd).expanduser() if arguments.cwd else context.cwd
        try:
            process = await create_shell_subprocess(
                arguments.command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except SandboxUnavailableError as exc:
            return ToolResult(output=str(exc), is_error=True)

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
