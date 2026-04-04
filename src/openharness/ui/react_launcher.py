"""Launch the default React terminal frontend."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path


def _resolve_npm() -> str:
    """Resolve the npm executable (npm.cmd on Windows)."""
    return shutil.which("npm") or "npm"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def get_frontend_dir() -> Path:
    """Return the React terminal frontend directory."""
    return _repo_root() / "frontend" / "terminal"


def build_backend_command(
    *,
    cwd: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    api_key: str | None = None,
    api_format: str | None = None,
) -> list[str]:
    """Return the command used by the React frontend to spawn the backend host."""
    command = [sys.executable, "-m", "openharness", "--backend-only"]
    if cwd:
        command.extend(["--cwd", cwd])
    if model:
        command.extend(["--model", model])
    if base_url:
        command.extend(["--base-url", base_url])
    if system_prompt:
        command.extend(["--system-prompt", system_prompt])
    if api_key:
        command.extend(["--api-key", api_key])
    if api_format:
        command.extend(["--api-format", api_format])
    return command


async def launch_react_tui(
    *,
    prompt: str | None = None,
    cwd: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    api_key: str | None = None,
    api_format: str | None = None,
) -> int:
    """Launch the React terminal frontend as the default UI."""
    frontend_dir = get_frontend_dir()
    package_json = frontend_dir / "package.json"
    if not package_json.exists():
        raise RuntimeError(f"React terminal frontend is missing: {package_json}")

    npm = _resolve_npm()

    if not (frontend_dir / "node_modules").exists():
        install = await asyncio.create_subprocess_exec(
            npm,
            "install",
            "--no-fund",
            "--no-audit",
            cwd=str(frontend_dir),
        )
        if await install.wait() != 0:
            raise RuntimeError("Failed to install React terminal frontend dependencies")

    env = os.environ.copy()
    env["OPENHARNESS_FRONTEND_CONFIG"] = json.dumps(
        {
            "backend_command": build_backend_command(
                cwd=cwd or str(Path.cwd()),
                model=model,
                base_url=base_url,
                system_prompt=system_prompt,
                api_key=api_key,
                api_format=api_format,
            ),
            "initial_prompt": prompt,
        }
    )
    process = await asyncio.create_subprocess_exec(
        npm,
        "exec",
        "--",
        "tsx",
        "src/index.tsx",
        cwd=str(frontend_dir),
        env=env,
        stdin=None,
        stdout=None,
        stderr=None,
    )
    return await process.wait()


__all__ = ["build_backend_command", "get_frontend_dir", "launch_react_tui"]
