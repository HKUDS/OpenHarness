"""Tests for shell resolution helpers."""

from __future__ import annotations

from openharness.utils.shell import resolve_shell_command


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
