"""Content search tool with a pure-Python fallback."""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class GrepToolInput(BaseModel):
    """Arguments for the grep tool."""

    pattern: str = Field(description="Regular expression to search for")
    root: str | None = Field(default=None, description="Search root directory")
    file_glob: str = Field(default="**/*")
    case_sensitive: bool = Field(default=True)
    limit: int = Field(default=200, ge=1, le=2000)


class GrepTool(BaseTool):
    """Search text files for a regex pattern."""

    name = "grep"
    description = "Search file contents with a regular expression."
    input_model = GrepToolInput

    def is_read_only(self, arguments: GrepToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: GrepToolInput, context: ToolExecutionContext) -> ToolResult:
        root = _resolve_path(context.cwd, arguments.root) if arguments.root else context.cwd
        # Prefer ripgrep for performance; fallback to Python when unavailable.
        matches = await _rg_grep(
            root=root,
            pattern=arguments.pattern,
            file_glob=arguments.file_glob,
            case_sensitive=arguments.case_sensitive,
            limit=arguments.limit,
        )
        if matches is not None:
            return ToolResult(output="\n".join(matches) if matches else "(no matches)")

        # Python fallback (kept for portability).
        flags = 0 if arguments.case_sensitive else re.IGNORECASE
        compiled = re.compile(arguments.pattern, flags)
        collected: list[str] = []

        for path in root.glob(arguments.file_glob):
            if len(collected) >= arguments.limit:
                break
            if not path.is_file():
                continue
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw:
                continue
            text = raw.decode("utf-8", errors="replace")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if compiled.search(line):
                    collected.append(f"{path.relative_to(root)}:{line_no}:{line}")
                    if len(collected) >= arguments.limit:
                        break

        if not collected:
            return ToolResult(output="(no matches)")
        return ToolResult(output="\n".join(collected))


def _resolve_path(base: Path, candidate: str | None) -> Path:
    path = Path(candidate or ".").expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


async def _rg_grep(
    *,
    root: Path,
    pattern: str,
    file_glob: str,
    case_sensitive: bool,
    limit: int,
) -> list[str] | None:
    """Return matches using ripgrep, or None if ripgrep is unavailable."""
    rg = shutil.which("rg")
    if not rg:
        return None

    include_hidden = (root / ".git").exists() or (root / ".gitignore").exists()
    cmd: list[str] = [
        rg,
        "--no-heading",
        "--line-number",
        "--color",
        "never",
    ]
    if include_hidden:
        cmd.append("--hidden")
    if not case_sensitive:
        cmd.append("-i")
    if file_glob:
        cmd.extend(["--glob", file_glob])
    # `--` ensures patterns like `-foo` aren't parsed as flags.
    cmd.extend(["--", pattern, "."])

    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    matches: list[str] = []
    try:
        assert process.stdout is not None
        while len(matches) < limit:
            raw = await process.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\n")
            if line:
                matches.append(line)
    finally:
        if len(matches) >= limit and process.returncode is None:
            process.terminate()
        await process.wait()

    # rg exits 0 when matches are found, 1 when none are found.
    # Any other return code indicates an error; fall back to Python.
    if process.returncode in {0, 1}:
        return matches
    return None
