"""Atomic file-write helpers for persistent state.

Every file under ``~/.openharness/`` that is rewritten during normal use —
credentials, settings, session snapshots, cron registry, memory index — must
be written atomically. A crash, SIGKILL, power loss, or out-of-disk error
during a naive :meth:`pathlib.Path.write_text` leaves a truncated file on
disk, and the next read silently returns ``{}`` (for credentials) or raises
:class:`json.JSONDecodeError` (for sessions). Both outcomes are recoverable
only by manual intervention.

The pattern implemented here is the standard temp-file-plus-rename dance:

1. Create a same-directory temp file (so the final :func:`os.replace` is a
   rename on the same filesystem, never a cross-filesystem copy).
2. Write the payload, ``flush`` and ``fsync``.
3. Apply the target POSIX mode while the file is still private.
4. :func:`os.replace` atomically swaps the temp file into place. On POSIX
   the kernel guarantees that any concurrent reader sees either the old
   inode or the new one, never a half-written one. Since Python 3.3
   :func:`os.replace` provides the same guarantee on Windows.

For read-modify-write sequences on shared files (credentials, settings, cron
registry), pair atomic writes with :func:`exclusive_file_lock` from
:mod:`openharness.swarm.lockfile` so two concurrent ``oh`` processes cannot
clobber each other's updates.
"""

from __future__ import annotations

import contextlib
import os
import stat
import tempfile
from pathlib import Path

__all__ = ["atomic_write_bytes", "atomic_write_text"]


def atomic_write_bytes(path: str | os.PathLike[str], data: bytes, *, mode: int | None = None) -> None:
    """Write ``data`` to ``path`` atomically.

    When ``mode`` is given, the final file is created with that POSIX mode
    even if it did not previously exist. When ``mode`` is ``None``, the
    existing file's mode is preserved; for new files the current umask
    determines the mode, matching the historical behaviour of
    :meth:`pathlib.Path.write_text`.
    """
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    target_mode = _resolve_target_mode(dst, mode)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{dst.name}.", suffix=".tmp", dir=str(dst.parent)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(data)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        _apply_mode(tmp_path, target_mode)
        os.replace(tmp_path, dst)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise


def atomic_write_text(
    path: str | os.PathLike[str],
    data: str,
    *,
    encoding: str = "utf-8",
    mode: int | None = None,
) -> None:
    """Text variant of :func:`atomic_write_bytes`."""
    atomic_write_bytes(path, data.encode(encoding), mode=mode)


def _resolve_target_mode(path: Path, explicit_mode: int | None) -> int:
    if explicit_mode is not None:
        return explicit_mode
    try:
        st = path.stat()
    except FileNotFoundError:
        current_umask = os.umask(0)
        os.umask(current_umask)
        return 0o666 & ~current_umask
    return stat.S_IMODE(st.st_mode)


def _apply_mode(path: Path, target_mode: int) -> None:
    try:
        os.chmod(path, target_mode)
    except OSError:
        # chmod can fail on Windows / FAT / some network mounts. The payload
        # is still intact; only permission enforcement is weakened.
        pass
