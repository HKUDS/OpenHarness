"""Cross-platform file locking utility.

Uses fcntl on Unix/Linux and msvcrt on Windows.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# Import platform-specific locking modules
if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


@contextmanager
def file_lock(lock_path: Path, exclusive: bool = True) -> Iterator[None]:
    """Acquire a file lock on *lock_path*.

    Args:
        lock_path: Path to the lock file.
        exclusive: If True, acquire an exclusive (write) lock.
                  If False, acquire a shared (read) lock.

    Yields:
        None when the lock is acquired.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)

    # Open in appropriate mode
    mode = "r+" if sys.platform == "win32" else "r"
    lock_file = open(lock_path, mode)

    try:
        if sys.platform == "win32":
            # Windows uses msvcrt.locking
            # LOCK_EX = 1 (exclusive), LOCK_SH = 0 (shared)
            # LOCK_NB = 2 (non-blocking) - we don't use this for blocking locks
            lock_mode = msvcrt.LK_LOCK if exclusive else msvcrt.LK_RLCK
            # LK_LOCK retries 10 times before raising error
            msvcrt.locking(lock_file.fileno(), lock_mode, 1)
        else:
            # Unix uses fcntl.flock
            operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(lock_file.fileno(), operation)

        yield

    finally:
        try:
            if sys.platform == "win32":
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()
