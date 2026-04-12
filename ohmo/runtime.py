"""Runtime helpers for ohmo."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from openharness.api.client import SupportsStreamingMessages
from openharness.engine.stream_events import AssistantTextDelta, AssistantTurnComplete, CompactProgressEvent, ErrorEvent, StatusEvent
from openharness.ui.backend_host import run_backend_host
from openharness.ui.runtime import build_runtime, close_runtime, handle_line, start_runtime
from openharness.ui.react_launcher import _resolve_npm, _resolve_tsx, get_frontend_dir

from ohmo.prompts import build_ohmo_system_prompt
from ohmo.session_storage import OhmoSessionBackend
from ohmo.workspace import get_plugins_dir, get_skills_dir, initialize_workspace


def _ohmo_extra_roots(workspace: str | Path | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    root = initialize_workspace(workspace)
    return ((str(get_skills_dir(root)),), (str(get_plugins_dir(root)),))


async def run_ohmo_backend(
    *,
    cwd: str | None = None,
    workspace: str | Path | None = None,
    model: str | None = None,
    max_turns: int | None = None,
    provider_profile: str | None = None,
    api_client: SupportsStreamingMessages | None = None,
    restore_messages: list[dict] | None = None,
    restore_tool_metadata: dict[str, object] | None = None,
    backend_only: bool = True,
) -> int:
    """Run the shared React backend host with ohmo workspace semantics."""
    del backend_only
    cwd_path = str(Path(cwd or Path.cwd()).resolve())
    workspace_root = initialize_workspace(workspace)
    extra_skill_dirs, extra_plugin_roots = _ohmo_extra_roots(workspace_root)
    return await run_backend_host(
        cwd=cwd_path,
        model=model,
        max_turns=max_turns,
        system_prompt=build_ohmo_system_prompt(cwd_path, workspace=workspace_root),
        active_profile=provider_profile,
        api_client=api_client,
        restore_messages=restore_messages,
        restore_tool_metadata=restore_tool_metadata,
        enforce_max_turns=max_turns is not None,
        session_backend=OhmoSessionBackend(workspace_root),
        extra_skill_dirs=extra_skill_dirs,
        extra_plugin_roots=extra_plugin_roots,
    )


def build_ohmo_backend_command(
    *,
    cwd: str | None = None,
    workspace: str | Path | None = None,
    model: str | None = None,
    max_turns: int | None = None,
    provider_profile: str | None = None,
) -> list[str]:
    """Return the backend command for the React terminal UI."""
    command = [sys.executable, "-m", "ohmo", "--backend-only"]
    if cwd:
        command.extend(["--cwd", cwd])
    if workspace:
        command.extend(["--workspace", str(workspace)])
    if model:
        command.extend(["--model", model])
    if max_turns is not None:
        command.extend(["--max-turns", str(max_turns)])
    if provider_profile:
        command.extend(["--profile", provider_profile])
    return command


async def launch_ohmo_react_tui(
    *,
    cwd: str | None = None,
    workspace: str | Path | None = None,
    model: str | None = None,
    max_turns: int | None = None,
    provider_profile: str | None = None,
) -> int:
    """Launch the shared React terminal UI with an ohmo backend."""
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

    cwd_path = str(Path(cwd or Path.cwd()).resolve())
    workspace_root = initialize_workspace(workspace)
    env = os.environ.copy()
    env["OPENHARNESS_FRONTEND_CONFIG"] = json.dumps(
        {
            "backend_command": build_ohmo_backend_command(
                cwd=cwd_path,
                workspace=workspace_root,
                model=model,
                max_turns=max_turns,
                provider_profile=provider_profile,
            ),
            "initial_prompt": None,
            "theme": "default",
        }
    )
    tsx_cmd = _resolve_tsx(frontend_dir)
    process = await asyncio.create_subprocess_exec(
        *tsx_cmd,
        "src/index.tsx",
        cwd=str(frontend_dir),
        env=env,
        stdin=None,
        stdout=None,
        stderr=None,
    )
    return await process.wait()


async def run_ohmo_print_mode(
    *,
    prompt: str,
    cwd: str | None = None,
    workspace: str | Path | None = None,
    model: str | None = None,
    max_turns: int | None = None,
    provider_profile: str | None = None,
) -> int:
    """Run a single ohmo prompt and print the assistant output."""
    cwd_path = str(Path(cwd or Path.cwd()).resolve())
    workspace_root = initialize_workspace(workspace)
    extra_skill_dirs, extra_plugin_roots = _ohmo_extra_roots(workspace_root)
    previous_cwd = Path.cwd()
    os.chdir(cwd_path)
    try:
        bundle = await build_runtime(
            model=model,
            max_turns=max_turns,
            system_prompt=build_ohmo_system_prompt(cwd_path, workspace=workspace_root),
            active_profile=provider_profile,
            session_backend=OhmoSessionBackend(workspace_root),
            enforce_max_turns=max_turns is not None,
            extra_skill_dirs=extra_skill_dirs,
            extra_plugin_roots=extra_plugin_roots,
        )
        await start_runtime(bundle)

        async def _print_system(message: str) -> None:
            print(message, file=sys.stderr)

        async def _render_event(event) -> None:
            if isinstance(event, AssistantTextDelta):
                sys.stdout.write(event.text)
                sys.stdout.flush()
            elif isinstance(event, AssistantTurnComplete):
                sys.stdout.write("\n")
                sys.stdout.flush()
            elif isinstance(event, ErrorEvent):
                print(event.message, file=sys.stderr)
            elif isinstance(event, CompactProgressEvent):
                if event.message:
                    print(event.message, file=sys.stderr)
            elif isinstance(event, StatusEvent):
                print(event.message, file=sys.stderr)

        async def _clear_output() -> None:
            return None

        await handle_line(
            bundle,
            prompt,
            print_system=_print_system,
            render_event=_render_event,
            clear_output=_clear_output,
        )
        await close_runtime(bundle)
        return 0
    finally:
        os.chdir(previous_cwd)
