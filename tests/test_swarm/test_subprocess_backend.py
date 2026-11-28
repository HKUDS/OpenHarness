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


@pytest.mark.asyncio
async def test_subprocess_backend_enforces_concurrency_cap_and_warns(
    monkeypatch, tmp_path: Path, caplog
):
    import asyncio
    import logging

    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    backend = SubprocessBackend(max_concurrent_teammates=2)

    running = 0
    max_running = 0
    spawned: list[str] = []

    configs = [
        TeammateSpawnConfig(
            name=f"worker-{idx}",
            team="cap-team",
            prompt="go",
            cwd=str(tmp_path),
            parent_session_id="sess-001",
            command=f"{sys.executable} -u -c \"import time; time.sleep(0.15)\"",
            task_type="local_agent",
        )
        for idx in range(4)
    ]

    from openharness.tasks.manager import get_task_manager

    manager = get_task_manager()
    orig_create = manager.create_agent_task

    async def _wrapped_create(**kwargs):
        nonlocal running, max_running
        record = await orig_create(**kwargs)
        running += 1
        max_running = max(max_running, running)
        spawned.append(record.id)
        return record

    async def _on_done(record):
        nonlocal running
        if record.id in spawned and record.status in {"completed", "failed", "killed"}:
            running -= 1

    monkeypatch.setattr(manager, "create_agent_task", _wrapped_create)
    unregister = manager.register_completion_listener(_on_done)
    try:
        with caplog.at_level(logging.WARNING, logger="openharness.swarm.subprocess_backend"):
            results = await asyncio.gather(*(backend.spawn(cfg) for cfg in configs))
    finally:
        unregister()

    assert all(res.success for res in results)
    assert len(spawned) == 4
    assert max_running <= 2
    assert any("share the parent API key" in rec.message for rec in caplog.records)

    # Wait for remaining background tasks to complete and release slots.
    deadline = asyncio.get_running_loop().time() + 5.0
    while asyncio.get_running_loop().time() < deadline:
        tasks = [manager.get_task(res.task_id) for res in results]
        if all(t is not None and t.status in {"completed", "failed", "killed"} for t in tasks):
            break
        await asyncio.sleep(0.05)

    assert backend._slot_releasers == {}


@pytest.mark.asyncio
async def test_subprocess_backend_releases_slot_when_spawn_fails(monkeypatch, tmp_path: Path):
    backend = SubprocessBackend(max_concurrent_teammates=1)
    calls = 0

    async def _flaky_create(self, **kwargs):
        nonlocal calls
        del kwargs
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        return TaskRecord(
            id="task_ok",
            type="local_agent",
            status="running",
            description="ok",
            cwd=str(tmp_path),
            output_file=tmp_path / "ok.log",
        )

    monkeypatch.setattr(BackgroundTaskManager, "create_agent_task", _flaky_create)

    cfg = TeammateSpawnConfig(
        name="worker",
        team="default",
        prompt="hi",
        cwd=str(tmp_path),
        parent_session_id="sess-001",
    )
    first = await backend.spawn(cfg)
    assert first.success is False

    # Slot must have been released on error so the next spawn succeeds immediately.
    second = await backend.spawn(cfg)
    assert second.success is True
    assert second.task_id == "task_ok"


@pytest.mark.asyncio
async def test_subprocess_backend_unlimited_mode_and_shutdown_frees_slot(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    # Unlimited (0) allows spawning without semaphore gating.
    unlimited = SubprocessBackend(max_concurrent_teammates=0)
    res_unlim = await unlimited.spawn(
        TeammateSpawnConfig(
            name="u1",
            team="t",
            prompt="hi",
            cwd=str(tmp_path),
            parent_session_id="s",
            command=f"{sys.executable} -u -c \"import time; time.sleep(0.05)\"",
        )
    )
    assert res_unlim.success is True
    assert unlimited._semaphore is None

    # Shutdown releases an active semaphore slot immediately.
    capped = SubprocessBackend(max_concurrent_teammates=1)
    r1 = await capped.spawn(
        TeammateSpawnConfig(
            name="c1",
            team="t",
            prompt="hi",
            cwd=str(tmp_path),
            parent_session_id="s",
            command=f"{sys.executable} -u -c \"import time; time.sleep(5)\"",
        )
    )
    assert r1.success is True
    assert await capped.shutdown("c1@t") is True
    assert capped._slot_releasers == {}

    r2 = await capped.spawn(
        TeammateSpawnConfig(
            name="c2",
            team="t",
            prompt="hi",
            cwd=str(tmp_path),
            parent_session_id="s",
            command=f"{sys.executable} -u -c \"print('ok')\"",
        )
    )
    assert r2.success is True
