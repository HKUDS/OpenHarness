"""Tests for openharness.prompts.environment."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from openharness.prompts.environment import (
    EnvironmentInfo,
    detect_git_info,
    detect_os,
    detect_shell,
    get_environment_info,
)


def test_detect_os_returns_tuple():
    os_name, os_version = detect_os()
    assert isinstance(os_name, str)
    assert isinstance(os_version, str)
    assert len(os_name) > 0


def test_detect_shell_returns_string(monkeypatch):
    monkeypatch.setenv("SHELL", "/bin/bash")
    assert detect_shell() == "bash"


def test_detect_shell_zsh(monkeypatch):
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    assert detect_shell() == "zsh"


def test_detect_shell_fallback(monkeypatch):
    monkeypatch.delenv("SHELL", raising=False)
    shell = detect_shell()
    # Should find something on PATH or return "unknown"
    assert isinstance(shell, str)


def test_detect_git_info_in_repo(tmp_path: Path):
    # Create a git repo
    os.system(f"git init {tmp_path} > /dev/null 2>&1")
    is_git, branch = detect_git_info(str(tmp_path))
    assert is_git is True
    # branch may be None for empty repo or "main"/"master"
    assert branch is None or isinstance(branch, str)


def test_detect_git_info_not_a_repo(tmp_path: Path):
    is_git, branch = detect_git_info(str(tmp_path))
    assert is_git is False
    assert branch is None


def test_detect_git_info_uses_devnull_for_git_subprocess(monkeypatch):
    calls: list[dict[str, object]] = []

    class _Completed:
        def __init__(self, returncode: int, stdout: str):
            self.returncode = returncode
            self.stdout = stdout

    def _fake_run(args, **kwargs):
        calls.append({"args": args, **kwargs})
        if args[-1] == "--is-inside-work-tree":
            return _Completed(0, "true\n")
        return _Completed(0, "main\n")

    monkeypatch.setattr("openharness.prompts.environment.subprocess.run", _fake_run)

    is_git, branch = detect_git_info("/tmp/project")

    assert is_git is True
    assert branch == "main"
    assert len(calls) == 2
    assert calls[0]["stdin"] is subprocess.DEVNULL
    assert calls[1]["stdin"] is subprocess.DEVNULL


def test_get_environment_info_returns_dataclass():
    info = get_environment_info()
    assert isinstance(info, EnvironmentInfo)
    assert len(info.os_name) > 0
    assert len(info.shell) > 0
    assert len(info.cwd) > 0
    assert len(info.date) == 10  # YYYY-MM-DD
    assert len(info.python_version) > 0
    assert len(info.python_executable) > 0


def test_get_environment_info_detects_virtual_env_from_python_executable(monkeypatch, tmp_path: Path):
    venv_root = tmp_path / ".openharness-venv"
    bin_dir = venv_root / "bin"
    bin_dir.mkdir(parents=True)
    (venv_root / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    fake_python = bin_dir / "python"
    fake_python.write_text("", encoding="utf-8")

    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr("openharness.prompts.environment.sys.executable", str(fake_python))

    info = get_environment_info(cwd=str(tmp_path))

    assert info.python_executable == str(fake_python.resolve())
    assert info.virtual_env == str(venv_root.resolve())


def test_get_environment_info_cwd_override(tmp_path: Path):
    info = get_environment_info(cwd=str(tmp_path))
    assert info.cwd == str(tmp_path)
