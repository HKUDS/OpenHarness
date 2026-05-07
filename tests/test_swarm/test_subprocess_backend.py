"""Tests for subprocess teammate spawning."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

from openharness.tasks.manager import BackgroundTaskManager
from openharness.tasks.types import TaskRecord
from openharness.swarm.subprocess_backend import SubprocessBackend
from openharness.swarm.types import TeammateSpawnConfig


def _argv_str(captured: dict) -> str:
    """Join captured argv into a string for substring assertions."""
    argv = captured.get("argv") or []
    return " ".join(argv)


@pytest.mark.asyncio
async def test_subprocess_backend_forwards_system_prompt_in_command(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    async def _fake_create_agent_task(self, **kwargs):
        captured.update(kwargs)
        return TaskRecord(
            id="task_123",
            type="local_agent",
            status="running",
            description=str(kwargs["description"]),
            cwd=str(kwargs["cwd"]),
            output_file=tmp_path / "task_123.log",
            argv=list(kwargs.get("argv") or []),
        )

    monkeypatch.setattr(BackgroundTaskManager, "create_agent_task", _fake_create_agent_task)
    monkeypatch.setattr("openharness.swarm.subprocess_backend.get_teammate_command", lambda: "/usr/bin/python3")

    backend = SubprocessBackend()
    config = TeammateSpawnConfig(
        name="reviewer",
        team="default",
        prompt="Review the code changes.",
        cwd=str(tmp_path),
        parent_session_id="sess-001",
        system_prompt="You are a careful code reviewer.",
        task_type="local_agent",
    )

    result = await backend.spawn(config)

    assert result.success is True
    argv_str = _argv_str(captured)
    assert "--system-prompt" in argv_str
    assert "You are a careful code reviewer." in argv_str


@pytest.mark.asyncio
async def test_subprocess_backend_forwards_append_system_prompt_mode(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    async def _fake_create_agent_task(self, **kwargs):
        captured.update(kwargs)
        return TaskRecord(
            id="task_234",
            type="local_agent",
            status="running",
            description=str(kwargs["description"]),
            cwd=str(kwargs["cwd"]),
            output_file=tmp_path / "task_234.log",
            argv=list(kwargs.get("argv") or []),
        )

    monkeypatch.setattr(BackgroundTaskManager, "create_agent_task", _fake_create_agent_task)
    monkeypatch.setattr("openharness.swarm.subprocess_backend.get_teammate_command", lambda: "/usr/bin/python3")

    backend = SubprocessBackend()
    config = TeammateSpawnConfig(
        name="reviewer",
        team="default",
        prompt="Review the code changes.",
        cwd=str(tmp_path),
        parent_session_id="sess-001",
        system_prompt="Project-specific addendum.",
        system_prompt_mode="append",
        task_type="local_agent",
    )

    result = await backend.spawn(config)

    assert result.success is True
    argv_str = _argv_str(captured)
    assert "--append-system-prompt" in argv_str
    assert "Project-specific addendum." in argv_str


@pytest.mark.asyncio
async def test_subprocess_backend_passes_argv_list_not_shell_command(
    monkeypatch, tmp_path: Path
):
    """Regression test for #230: teammate spawn must use the direct-exec
    ``argv`` path, not the shell-evaluated ``command`` path. Shell routing
    via Git Bash on Windows cannot reliably exec Windows-pathed binaries
    (e.g. ``C:\\Users\\...\\python.exe``) when bash is itself launched via
    ``asyncio.create_subprocess_exec`` — the same call that works
    interactively returns ``command not found``. Bypassing the shell
    sidesteps the entire class of cross-platform quoting bug."""
    captured: dict[str, object] = {}

    async def _fake_create_agent_task(self, **kwargs):
        captured.update(kwargs)
        return TaskRecord(
            id="task_argv",
            type="local_agent",
            status="running",
            description=str(kwargs["description"]),
            cwd=str(kwargs["cwd"]),
            output_file=tmp_path / "task_argv.log",
            argv=list(kwargs.get("argv") or []),
        )

    monkeypatch.setattr(BackgroundTaskManager, "create_agent_task", _fake_create_agent_task)

    backend = SubprocessBackend()
    config = TeammateSpawnConfig(
        name="worker",
        team="default",
        prompt="hi",
        cwd=str(tmp_path),
        parent_session_id="sess-001",
        task_type="local_agent",
    )
    result = await backend.spawn(config)

    assert result.success is True
    # Spawn must hand off as argv, not command.
    assert captured.get("command") is None
    argv = captured.get("argv")
    assert isinstance(argv, list) and argv, "expected non-empty argv list"
    # First element is the exact Python interpreter selected for teammate spawn.
    assert argv[0] == sys.executable
    # Tail must include the worker invocation.
    assert "--task-worker" in argv


@pytest.mark.asyncio
async def test_subprocess_backend_argv_preserves_windows_backslashes(
    monkeypatch, tmp_path: Path
):
    """When ``get_teammate_command()`` returns a Windows path with
    backslashes, those backslashes must arrive at the manager intact.
    Using a list (``argv``) instead of a shell-evaluated string is what
    makes that guarantee — there is no shell escape parser between us
    and ``asyncio.create_subprocess_exec``."""
    captured: dict[str, object] = {}

    async def _fake_create_agent_task(self, **kwargs):
        captured.update(kwargs)
        return TaskRecord(
            id="task_winargv",
            type="local_agent",
            status="running",
            description=str(kwargs["description"]),
            cwd=str(kwargs["cwd"]),
            output_file=tmp_path / "task_winargv.log",
            argv=list(kwargs.get("argv") or []),
        )

    win_path = r"C:\Users\simu\AppData\Roaming\uv\tools\openharness-ai\Scripts\python.exe"
    monkeypatch.setattr(BackgroundTaskManager, "create_agent_task", _fake_create_agent_task)
    # Use the public override env var rather than monkeypatching the
    # function symbol — proved fragile under full-suite pytest module
    # attribute resolution.
    monkeypatch.setenv("OPENHARNESS_TEAMMATE_COMMAND", win_path)

    backend = SubprocessBackend()
    config = TeammateSpawnConfig(
        name="worker",
        team="default",
        prompt="hi",
        cwd=str(tmp_path),
        parent_session_id="sess-001",
        task_type="local_agent",
    )
    result = await backend.spawn(config)

    assert result.success is True
    argv = captured.get("argv") or []
    assert argv[0] == win_path, f"backslashed path mangled: {argv[0]!r}"


@pytest.mark.asyncio
async def test_subprocess_backend_passes_env_via_kwarg(
    monkeypatch, tmp_path: Path
):
    """Inherited teammate env vars must flow through ``env=`` on
    ``create_agent_task`` and never be embedded in argv as ``KEY=val``
    tokens (which the OS would just pass to the child as plain args)."""
    captured: dict[str, object] = {}

    async def _fake_create_agent_task(self, **kwargs):
        captured.update(kwargs)
        return TaskRecord(
            id="task_env",
            type="local_agent",
            status="running",
            description=str(kwargs["description"]),
            cwd=str(kwargs["cwd"]),
            output_file=tmp_path / "task_env.log",
            argv=list(kwargs.get("argv") or []),
        )

    monkeypatch.setattr(BackgroundTaskManager, "create_agent_task", _fake_create_agent_task)
    monkeypatch.setattr(
        "openharness.swarm.subprocess_backend.get_teammate_command",
        lambda: "/usr/bin/python3",
    )

    backend = SubprocessBackend()
    config = TeammateSpawnConfig(
        name="worker",
        team="default",
        prompt="hi",
        cwd=str(tmp_path),
        parent_session_id="sess-001",
        task_type="local_agent",
    )
    result = await backend.spawn(config)

    assert result.success is True
    argv = captured.get("argv") or []
    # No element of argv should look like a shell env-prefix token.
    for token in argv:
        assert "OPENHARNESS_AGENT_TEAMS=" not in token
        assert "CLAUDE_CODE_COORDINATOR_MODE=" not in token
    env = captured.get("env")
    assert isinstance(env, dict)
    assert env.get("OPENHARNESS_AGENT_TEAMS") == "1"


@pytest.mark.asyncio
async def test_subprocess_backend_does_not_inject_env_when_command_overridden(
    monkeypatch, tmp_path: Path
):
    """When the caller supplies ``config.command``, we do not silently
    inject inherited env vars and we use the shell-evaluated path (not
    the argv path). This preserves caller intent and pre-fix behaviour
    for code that already builds its own shell-quoted command string."""
    captured: dict[str, object] = {}

    async def _fake_create_agent_task(self, **kwargs):
        captured.update(kwargs)
        return TaskRecord(
            id="task_override",
            type="local_agent",
            status="running",
            description=str(kwargs["description"]),
            cwd=str(kwargs["cwd"]),
            output_file=tmp_path / "task_override.log",
            command=str(kwargs.get("command") or ""),
        )

    monkeypatch.setattr(BackgroundTaskManager, "create_agent_task", _fake_create_agent_task)

    backend = SubprocessBackend()
    config = TeammateSpawnConfig(
        name="worker",
        team="default",
        prompt="hi",
        cwd=str(tmp_path),
        parent_session_id="sess-001",
        command="custom-script --do-it",
        task_type="local_agent",
    )
    result = await backend.spawn(config)

    assert result.success is True
    assert captured["command"] == "custom-script --do-it"
    assert captured.get("argv") is None
    assert captured.get("env") is None
