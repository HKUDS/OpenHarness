"""Cross-platform file-lock helpers for swarm mailbox and permission storage."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from openharness.platforms import PlatformName, get_platform


class SwarmLockError(RuntimeError):
    """Base error for swarm lock failures."""


class SwarmLockUnavailableError(SwarmLockError):
    """Raised when file locking is unavailable on the current platform."""


@contextmanager
def exclusive_file_lock(
    lock_path: Path,
    *,
    platform_name: PlatformName | None = None,
) -> Iterator[None]:
    """Acquire an exclusive file lock for swarm mailbox/permission operations."""
    resolved_platform = platform_name or get_platform()
    if resolved_platform == "windows":
        with _exclusive_windows_lock(lock_path):
            yield
        return
    if resolved_platform in {"macos", "linux", "wsl"}:
        with _exclusive_posix_lock(lock_path):
            yield
        return
    raise SwarmLockUnavailableError(
        f"swarm file locking is not supported on platform {resolved_platform!r}"
    )


@contextmanager
def _exclusive_posix_lock(lock_path: Path) -> Iterator[None]:
    try:
        import fcntl
    except ImportError as e:
        raise SwarmLockUnavailableError(f"fcntl not available: {e}") from e

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def _exclusive_windows_lock(lock_path: Path) -> Iterator[None]:
    try:
        import msvcrt
    except ImportError as e:
        raise SwarmLockUnavailableError(f"msvcrt not available: {e}") from e

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        # msvcrt.locking requires a byte range to exist and the file be open in
        # binary mode. Lock the first byte for the lifetime of the critical section.
        lock_file.seek(0)
        if lock_path.stat().st_size == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
