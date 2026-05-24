"""Tests for swarm file-lock helpers."""

from __future__ import annotations

import builtins
from contextlib import contextmanager
from pathlib import Path

import pytest

from openharness.swarm import lockfile
from openharness.utils import file_lock


def test_exclusive_file_lock_creates_lock_file_on_posix(tmp_path: Path):
    lock_path = tmp_path / "locks" / "mailbox.lock"

    with lockfile.exclusive_file_lock(lock_path, platform_name="linux"):
        assert lock_path.exists()

    assert lock_path.exists()


def test_exclusive_file_lock_routes_windows_branch(monkeypatch, tmp_path: Path):
    calls: list[Path] = []

    @contextmanager
    def _fake_windows_lock(lock_path: Path):
        calls.append(lock_path)
        yield

    # The implementation lives in ``openharness.utils.file_lock``;
    # ``openharness.swarm.lockfile`` re-exports it for backwards compatibility.
    monkeypatch.setattr(file_lock, "_exclusive_windows_lock", _fake_windows_lock)

    lock_path = tmp_path / "windows.lock"
    with lockfile.exclusive_file_lock(lock_path, platform_name="windows"):
        pass

    assert calls == [lock_path]


def test_exclusive_file_lock_rejects_unknown_platform(tmp_path: Path):
    with pytest.raises(lockfile.SwarmLockUnavailableError, match="not supported"):
        with lockfile.exclusive_file_lock(tmp_path / "unknown.lock", platform_name="unknown"):
            pass


def test_posix_lock_reports_unavailable_when_fcntl_missing(monkeypatch, tmp_path: Path):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "fcntl":
            raise ImportError("missing fcntl")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(lockfile.SwarmLockUnavailableError, match="fcntl not available"):
        with file_lock._exclusive_posix_lock(tmp_path / "posix.lock"):
            pass


def test_windows_lock_reports_unavailable_when_msvcrt_missing(monkeypatch, tmp_path: Path):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "msvcrt":
            raise ImportError("missing msvcrt")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(lockfile.SwarmLockUnavailableError, match="msvcrt not available"):
        with file_lock._exclusive_windows_lock(tmp_path / "windows.lock"):
            pass


def test_swarm_lockfile_shim_re_exports_public_api():
    """Existing callers importing from ``swarm.lockfile`` must keep working."""
    assert lockfile.exclusive_file_lock is file_lock.exclusive_file_lock
    assert lockfile.SwarmLockError is file_lock.SwarmLockError
    assert lockfile.SwarmLockUnavailableError is file_lock.SwarmLockUnavailableError
