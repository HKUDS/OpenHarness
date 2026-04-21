"""Tests for the Docker sandbox backend."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from openharness.config.settings import (
    DockerSandboxSettings,
    SandboxNetworkSettings,
    SandboxSettings,
    Settings,
)
from openharness.sandbox.docker_backend import (
    DockerSandboxSession,
    get_docker_availability,
)


# ---------------------------------------------------------------------------
# get_docker_availability
# ---------------------------------------------------------------------------


def test_docker_availability_disabled_when_backend_is_srt():
    settings = Settings(sandbox=SandboxSettings(enabled=True, backend="srt"))
    result = get_docker_availability(settings)
    assert result.available is False
    assert result.enabled is False


def test_docker_availability_disabled_when_sandbox_off():
    settings = Settings(sandbox=SandboxSettings(enabled=False, backend="docker"))
    result = get_docker_availability(settings)
    assert result.available is False


def test_docker_availability_when_not_installed(monkeypatch):
    settings = Settings(sandbox=SandboxSettings(enabled=True, backend="docker"))
    monkeypatch.setattr("openharness.sandbox.docker_backend.get_platform", lambda: "linux")
    monkeypatch.setattr("openharness.sandbox.docker_backend.shutil.which", lambda name: None)

    result = get_docker_availability(settings)
    assert result.available is False
    assert "not found" in (result.reason or "")


def test_docker_availability_when_daemon_not_running(monkeypatch):
    settings = Settings(sandbox=SandboxSettings(enabled=True, backend="docker"))
    monkeypatch.setattr("openharness.sandbox.docker_backend.get_platform", lambda: "linux")
    monkeypatch.setattr(
        "openharness.sandbox.docker_backend.shutil.which",
        lambda name: "/usr/bin/docker",
    )

    import subprocess

    monkeypatch.setattr(
        "openharness.sandbox.docker_backend.subprocess.run",
        MagicMock(side_effect=subprocess.CalledProcessError(1, "docker info")),
    )

    result = get_docker_availability(settings)
    assert result.available is False
    assert "not running" in (result.reason or "")


def test_docker_availability_when_platform_unsupported(monkeypatch):
    settings = Settings(sandbox=SandboxSettings(enabled=True, backend="docker"))
    monkeypatch.setattr("openharness.sandbox.docker_backend.get_platform", lambda: "windows")

    result = get_docker_availability(settings)
    assert result.available is False
    assert "not supported" in (result.reason or "")


def test_docker_availability_when_all_ok(monkeypatch):
    settings = Settings(sandbox=SandboxSettings(enabled=True, backend="docker"))
    monkeypatch.setattr("openharness.sandbox.docker_backend.get_platform", lambda: "linux")
    monkeypatch.setattr(
        "openharness.sandbox.docker_backend.shutil.which",
        lambda name: "/usr/bin/docker",
    )
    monkeypatch.setattr(
        "openharness.sandbox.docker_backend.subprocess.run",
        MagicMock(return_value=MagicMock(returncode=0)),
    )

    result = get_docker_availability(settings)
    assert result.available is True
    assert result.enabled is True


# ---------------------------------------------------------------------------
# DockerSandboxSession._build_run_argv
# ---------------------------------------------------------------------------


def test_container_start_builds_correct_docker_args(monkeypatch):
    monkeypatch.setattr(
        "openharness.sandbox.docker_backend.shutil.which",
        lambda name: "/usr/bin/docker",
    )
    settings = Settings(sandbox=SandboxSettings(enabled=True, backend="docker"))
    session = DockerSandboxSession(settings=settings, session_id="abc123", cwd=Path("/repo"))

    argv = session._build_run_argv()

    assert argv[0] == "/usr/bin/docker"
    assert "run" in argv
    assert "--rm" in argv
    assert "--name" in argv
    name_idx = argv.index("--name")
    assert argv[name_idx + 1] == "openharness-sandbox-abc123"
    assert "tail" in argv
    assert "-f" in argv
    assert "/dev/null" in argv


def test_network_none_by_default(monkeypatch):
    monkeypatch.setattr(
        "openharness.sandbox.docker_backend.shutil.which",
        lambda name: "/usr/bin/docker",
    )
    settings = Settings(sandbox=SandboxSettings(enabled=True, backend="docker"))
    session = DockerSandboxSession(settings=settings, session_id="abc", cwd=Path("/repo"))

    argv = session._build_run_argv()

    net_idx = argv.index("--network")
    assert argv[net_idx + 1] == "none"


def test_network_none_and_warning_when_domain_policy_is_configured(monkeypatch, caplog):
    monkeypatch.setattr(
        "openharness.sandbox.docker_backend.shutil.which",
        lambda name: "/usr/bin/docker",
    )
    settings = Settings(
        sandbox=SandboxSettings(
            enabled=True,
            backend="docker",
            network=SandboxNetworkSettings(
                allowed_domains=["github.com"],
                denied_domains=["example.com"],
            ),
        )
    )
    session = DockerSandboxSession(settings=settings, session_id="abc", cwd=Path("/repo"))

    argv = session._build_run_argv()

    net_idx = argv.index("--network")
    assert argv[net_idx + 1] == "none"
    assert "does not enforce allowed_domains/denied_domains yet" in caplog.text


def test_resource_limits_applied(monkeypatch):
    monkeypatch.setattr(
        "openharness.sandbox.docker_backend.shutil.which",
        lambda name: "/usr/bin/docker",
    )
    settings = Settings(
        sandbox=SandboxSettings(
            enabled=True,
            backend="docker",
            docker=DockerSandboxSettings(cpu_limit=2.0, memory_limit="4g"),
        )
    )
    session = DockerSandboxSession(settings=settings, session_id="abc", cwd=Path("/repo"))

    argv = session._build_run_argv()

    cpus_idx = argv.index("--cpus")
    assert argv[cpus_idx + 1] == "2.0"
    mem_idx = argv.index("--memory")
    assert argv[mem_idx + 1] == "4g"


def test_resource_limits_omitted_when_zero(monkeypatch):
    monkeypatch.setattr(
        "openharness.sandbox.docker_backend.shutil.which",
        lambda name: "/usr/bin/docker",
    )
    settings = Settings(sandbox=SandboxSettings(enabled=True, backend="docker"))
    session = DockerSandboxSession(settings=settings, session_id="abc", cwd=Path("/repo"))

    argv = session._build_run_argv()

    assert "--cpus" not in argv
    assert "--memory" not in argv


def test_bind_mount_uses_same_path(monkeypatch):
    monkeypatch.setattr(
        "openharness.sandbox.docker_backend.shutil.which",
        lambda name: "/usr/bin/docker",
    )
    settings = Settings(sandbox=SandboxSettings(enabled=True, backend="docker"))
    cwd = Path("/home/user/project")
    session = DockerSandboxSession(settings=settings, session_id="abc", cwd=cwd)

    argv = session._build_run_argv()

    resolved = str(cwd.resolve())
    assert f"{resolved}:{resolved}" in argv


# ---------------------------------------------------------------------------
# exec_command
# ---------------------------------------------------------------------------


async def test_exec_command_delegates_to_docker_exec(monkeypatch):
    monkeypatch.setattr(
        "openharness.sandbox.docker_backend.shutil.which",
        lambda name: "/usr/bin/docker",
    )
    settings = Settings(sandbox=SandboxSettings(enabled=True, backend="docker"))
    session = DockerSandboxSession(settings=settings, session_id="abc", cwd=Path("/repo"))
    session._running = True

    captured_args: list[str] = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured_args.extend(args)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        return mock_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    await session.exec_command(
        ["bash", "-lc", "echo hello"],
        cwd="/repo",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    assert captured_args[0] == "/usr/bin/docker"
    assert captured_args[1] == "exec"
    assert "openharness-sandbox-abc" in captured_args
    assert "bash" in captured_args


async def test_exec_command_raises_when_not_running(monkeypatch):
    monkeypatch.setattr(
        "openharness.sandbox.docker_backend.shutil.which",
        lambda name: "/usr/bin/docker",
    )
    settings = Settings(sandbox=SandboxSettings(enabled=True, backend="docker"))
    session = DockerSandboxSession(settings=settings, session_id="abc", cwd=Path("/repo"))
    # _running is False by default

    from openharness.sandbox.adapter import SandboxUnavailableError

    with pytest.raises(SandboxUnavailableError):
        await session.exec_command(["echo", "hi"], cwd="/repo")


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------


async def test_stop_calls_docker_stop(monkeypatch):
    monkeypatch.setattr(
        "openharness.sandbox.docker_backend.shutil.which",
        lambda name: "/usr/bin/docker",
    )
    settings = Settings(sandbox=SandboxSettings(enabled=True, backend="docker"))
    session = DockerSandboxSession(settings=settings, session_id="abc", cwd=Path("/repo"))
    session._running = True

    captured: list[str] = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured.extend(args)
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0
        return mock_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    await session.stop()

    assert "stop" in captured
    assert "openharness-sandbox-abc" in captured
    assert session.is_running is False
