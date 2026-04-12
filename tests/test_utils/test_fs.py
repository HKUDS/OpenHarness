"""Tests for :mod:`openharness.utils.fs` atomic-write helpers."""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import stat
import sys
from pathlib import Path

import pytest

from openharness.utils.fs import atomic_write_bytes, atomic_write_text


# ---------------------------------------------------------------------------
# Core behaviour
# ---------------------------------------------------------------------------


def test_atomic_write_text_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    atomic_write_text(path, '{"hello": "world"}\n')
    assert path.read_text() == '{"hello": "world"}\n'


def test_atomic_write_bytes_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "out.bin"
    atomic_write_bytes(path, b"\x00\x01\x02")
    assert path.read_bytes() == b"\x00\x01\x02"


def test_atomic_write_creates_parent_directory(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "deep" / "out.txt"
    atomic_write_text(path, "hi")
    assert path.read_text() == "hi"


def test_atomic_write_overwrites_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "out.txt"
    path.write_text("old contents")
    atomic_write_text(path, "new contents")
    assert path.read_text() == "new contents"


def test_atomic_write_does_not_leave_tempfiles(tmp_path: Path) -> None:
    path = tmp_path / "out.txt"
    atomic_write_text(path, "payload")
    assert path.exists()
    leftover = [p for p in tmp_path.iterdir() if p != path]
    assert leftover == []


# ---------------------------------------------------------------------------
# Mode handling
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes not enforced on Windows")
def test_mode_is_applied_to_new_file(tmp_path: Path) -> None:
    path = tmp_path / "creds.json"
    atomic_write_text(path, "secret", mode=0o600)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes not enforced on Windows")
def test_credentials_are_never_world_readable(tmp_path: Path) -> None:
    """Regression test: the file must be 0o600 from the very first byte.

    The previous ``write_text`` + ``chmod`` sequence left a window during
    which a co-resident attacker could stat the file with the default umask
    mode (commonly 0o644). The atomic helper closes that window by applying
    the mode before the tempfile is renamed into place.
    """
    path = tmp_path / "credentials.json"
    atomic_write_text(
        path,
        json.dumps({"anthropic": {"api_key": "sk-secret"}}),
        mode=0o600,
    )
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode & 0o077 == 0, f"file is readable by group/other: {oct(mode)}"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes not enforced on Windows")
def test_mode_preserved_on_overwrite_when_not_specified(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}")
    os.chmod(path, 0o640)
    atomic_write_text(path, '{"updated": true}')
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes not enforced on Windows")
def test_explicit_mode_overrides_existing_mode(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    path.write_text("{}")
    os.chmod(path, 0o644)
    atomic_write_text(path, "{}", mode=0o600)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


# ---------------------------------------------------------------------------
# Atomicity under write failure
# ---------------------------------------------------------------------------


def test_existing_file_is_untouched_on_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the write raises before ``os.replace`` runs, the old file survives."""
    path = tmp_path / "settings.json"
    path.write_text('{"kept": true}')

    def _boom(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("openharness.utils.fs.os.replace", _boom)

    with pytest.raises(OSError, match="disk full"):
        atomic_write_text(path, '{"overwritten": true}')

    assert json.loads(path.read_text()) == {"kept": True}
    leftover = sorted(p.name for p in tmp_path.iterdir() if p != path)
    assert leftover == [], f"tempfile leaked: {leftover}"


# ---------------------------------------------------------------------------
# Concurrent writers (end-to-end — exercises lock + atomic write together)
# ---------------------------------------------------------------------------


def _concurrent_writer(target_path: str, lock_path: str, key: str, value: str) -> None:
    """Read-modify-write entry point for :func:`test_concurrent_writers_all_survive`.

    Must be a module-level function so it is picklable by ``multiprocessing``.
    """
    from openharness.utils.file_lock import exclusive_file_lock
    from openharness.utils.fs import atomic_write_text

    target = Path(target_path)
    lock = Path(lock_path)
    with exclusive_file_lock(lock):
        if target.exists():
            data = json.loads(target.read_text())
        else:
            data = {}
        data[key] = value
        atomic_write_text(target, json.dumps(data, indent=2) + "\n")


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX fork semantics keep this test deterministic; skip on Windows CI",
)
def test_concurrent_writers_all_survive(tmp_path: Path) -> None:
    """Two concurrent read-modify-write processes must not lose updates."""
    target = tmp_path / "credentials.json"
    lock = tmp_path / "credentials.json.lock"

    ctx = mp.get_context("fork")
    writers = [
        ctx.Process(target=_concurrent_writer, args=(str(target), str(lock), f"key_{i}", f"value_{i}"))
        for i in range(8)
    ]
    for w in writers:
        w.start()
    for w in writers:
        w.join(timeout=10)
        assert w.exitcode == 0, f"writer {w.pid} failed with exit code {w.exitcode}"

    result = json.loads(target.read_text())
    assert set(result) == {f"key_{i}" for i in range(8)}
    assert all(result[f"key_{i}"] == f"value_{i}" for i in range(8))
