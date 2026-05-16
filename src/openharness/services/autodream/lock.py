"""Locking and session scanning for auto-dream."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from openharness.memory.paths import get_project_memory_dir
from openharness.services.session_storage import get_project_session_dir
from openharness.utils.fs import atomic_write_text

LOCK_FILE = ".consolidate-lock"
HOLDER_STALE_SECONDS = 60 * 60


def _lock_path(cwd: str | Path, memory_dir: str | Path | None = None) -> Path:
    return Path(memory_dir) / LOCK_FILE if memory_dir is not None else get_project_memory_dir(cwd) / LOCK_FILE


def read_last_consolidated_at(cwd: str | Path, memory_dir: str | Path | None = None) -> float:
    """Return lock mtime as the last successful consolidation timestamp."""

    try:
        return _lock_path(cwd, memory_dir).stat().st_mtime
    except OSError:
        return 0.0


def _holder_pid(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        pid = int(raw)
    except (OSError, ValueError):
        return None
    return pid if pid > 0 else None


def _is_process_running(pid: int) -> bool:
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def try_acquire_consolidation_lock(cwd: str | Path, memory_dir: str | Path | None = None) -> float | None:
    """Acquire the consolidation lock and return prior mtime, or None if held."""

    path = _lock_path(cwd, memory_dir)
    prior_mtime: float | None = None
    try:
        stat = path.stat()
        prior_mtime = stat.st_mtime
        holder = _holder_pid(path)
    except OSError:
        holder = None

    if prior_mtime is not None and time.time() - prior_mtime < HOLDER_STALE_SECONDS:
        if holder is not None and _is_process_running(holder):
            return None

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, f"{os.getpid()}\n")
    try:
        if _holder_pid(path) != os.getpid():
            return None
    except OSError:
        return None
    return prior_mtime or 0.0


def rollback_consolidation_lock(
    cwd: str | Path,
    prior_mtime: float,
    memory_dir: str | Path | None = None,
) -> None:
    """Restore lock mtime to its pre-acquire value after failed/killed dream."""

    path = _lock_path(cwd, memory_dir)
    try:
        if prior_mtime <= 0:
            path.unlink(missing_ok=True)
            return
        atomic_write_text(path, "")
        os.utime(path, (prior_mtime, prior_mtime))
    except OSError:
        # Best effort: a failed rollback only delays the next auto trigger.
        return


def record_consolidation(cwd: str | Path, memory_dir: str | Path | None = None) -> None:
    """Stamp a manual consolidation time."""

    path = _lock_path(cwd, memory_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, f"{os.getpid()}\n")


def list_sessions_touched_since(
    cwd: str | Path,
    since_ts: float,
    *,
    current_session_id: str | None = None,
    session_dir: str | Path | None = None,
) -> list[str]:
    """Return saved session IDs whose snapshot files were touched after ``since_ts``."""

    resolved_session_dir = Path(session_dir) if session_dir is not None else get_project_session_dir(cwd)
    session_ids: list[str] = []
    seen: set[str] = set()
    for path in sorted(resolved_session_dir.glob("session-*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime <= since_ts:
            continue
        session_id = path.stem.removeprefix("session-")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            raw_id = payload.get("session_id")
            if isinstance(raw_id, str) and raw_id.strip():
                session_id = raw_id.strip()
        except (OSError, json.JSONDecodeError):
            pass
        if current_session_id and session_id == current_session_id:
            continue
        if session_id in seen:
            continue
        seen.add(session_id)
        session_ids.append(session_id)
    return session_ids
