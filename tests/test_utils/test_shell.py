"""Tests for shell resolution helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from openharness.config.settings import Settings
from openharness.utils.shell import create_shell_subprocess, resolve_shell_command


def test_resolve_shell_command_prefers_bash_on_linux(monkeypatch):
    monkeypatch.setattr(
        "openharness.utils.shell.shutil.which",
        lambda name: "/usr/bin/bash" if name == "bash" else None,
    )

    command = resolve_shell_command("echo hi", platform_name="linux")

    assert command == ["/usr/bin/bash", "-lc", "echo hi"]


def test_resolve_shell_command_wraps_with_script_when_pty_requested(monkeypatch):
    def fake_which(name: str) -> str | None:
        mapping = {
            "bash": "/usr/bin/bash",
            "script": "/usr/bin/script",
        }
        return mapping.get(name)

    monkeypatch.setattr("openharness.utils.shell.shutil.which", fake_which)

    command = resolve_shell_command("echo hi", platform_name="linux", prefer_pty=True)

    assert command == ["/usr/bin/script", "-qefc", "echo hi", "/dev/null"]


def test_resolve_shell_command_uses_powershell_on_windows(monkeypatch):
    def fake_which(name: str) -> str | None:
        mapping = {
            "pwsh": "C:/Program Files/PowerShell/7/pwsh.exe",
        }
        return mapping.get(name)

    monkeypatch.setattr("openharness.utils.shell.shutil.which", fake_which)

    command = resolve_shell_command("Write-Output hi", platform_name="windows")

    assert command == [
        "C:/Program Files/PowerShell/7/pwsh.exe",
        "-NoLogo",
        "-NoProfile",
        "-Command",
        "Write-Output hi",
    ]


def test_resolve_shell_command_skips_script_on_macos(monkeypatch):
    def fake_which(name: str) -> str | None:
        mapping = {
            "bash": "/bin/bash",
            "script": "/usr/bin/script",
        }
        return mapping.get(name)

    monkeypatch.setattr("openharness.utils.shell.shutil.which", fake_which)

    command = resolve_shell_command("echo hi", platform_name="macos", prefer_pty=True)

    assert command == ["/bin/bash", "-lc", "echo hi"]


def test_resolve_shell_command_linux_without_script_falls_back(monkeypatch):
    def fake_which(name: str) -> str | None:
        mapping = {
            "bash": "/usr/bin/bash",
        }
        return mapping.get(name)

    monkeypatch.setattr("openharness.utils.shell.shutil.which", fake_which)

    command = resolve_shell_command("echo hi", platform_name="linux", prefer_pty=True)

    assert command == ["/usr/bin/bash", "-lc", "echo hi"]


@pytest.mark.asyncio
async def test_create_shell_subprocess_defaults_stdin_to_devnull(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

        class _FakeProcess:
            returncode = 0

            async def wait(self):
                return 0

        return _FakeProcess()

    monkeypatch.setattr(
        "openharness.utils.shell.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    monkeypatch.setattr(
        "openharness.utils.shell.wrap_command_for_sandbox",
        lambda argv, settings=None: (argv, None),
    )
    monkeypatch.setattr(
        "openharness.utils.shell.shutil.which",
        lambda name: "/usr/bin/bash" if name == "bash" else None,
    )

    await create_shell_subprocess(
        "echo hi",
        cwd=tmp_path,
        settings=Settings(),
    )

    assert captured["args"] == ("/usr/bin/bash", "-lc", "echo hi")
    assert captured["kwargs"]["stdin"] is asyncio.subprocess.DEVNULL
