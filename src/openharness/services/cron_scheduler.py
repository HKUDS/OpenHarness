"""Background cron scheduler daemon.

Runs as a standalone process (``oh cron start``) or can be embedded via
:func:`run_scheduler_loop`.  Every tick it reads the cron registry, checks
which enabled jobs are due, executes them, and records results in a history
log.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openharness.config.paths import get_data_dir, get_logs_dir
from openharness.services.cron import (
    load_cron_jobs,
    mark_job_run,
    validate_cron_expression,
)

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 30
"""How often the scheduler checks for due jobs."""


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------

def get_history_path() -> Path:
    """Return the path to the cron execution history file."""
    return get_data_dir() / "cron_history.jsonl"


def append_history(entry: dict[str, Any]) -> None:
    """Append one execution record to the history log."""
    path = get_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def load_history(*, limit: int = 50, job_name: str | None = None) -> list[dict[str, Any]]:
    """Load the most recent execution history entries."""
    path = get_history_path()
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if job_name and entry.get("name") != job_name:
            continue
        entries.append(entry)
    return entries[-limit:]


# ---------------------------------------------------------------------------
# PID file helpers
# ---------------------------------------------------------------------------

def get_pid_path() -> Path:
    """Return the scheduler PID file path."""
    return get_data_dir() / "cron_scheduler.pid"


def read_pid() -> int | None:
    """Read the PID of a running scheduler, or None."""
    path = get_pid_path()
    if not path.exists():
        return None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None
    # Check if process is alive
    try:
        os.kill(pid, 0)
    except OSError:
        logger.debug("Removed stale scheduler PID file (pid=%d)", pid)
        path.unlink(missing_ok=True)
        return None
    return pid


def write_pid() -> None:
    """Write the current process PID."""
    path = get_pid_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()) + "\n", encoding="utf-8")


def remove_pid() -> None:
    """Remove the PID file."""
    get_pid_path().unlink(missing_ok=True)


def is_scheduler_running() -> bool:
    """Return True if a scheduler process is alive."""
    return read_pid() is not None


def stop_scheduler() -> bool:
    """Send SIGTERM to the running scheduler. Returns True if killed."""
    pid = read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        remove_pid()
        return False
    # Wait briefly for process to exit
    for _ in range(10):
        try:
            os.kill(pid, 0)
        except OSError:
            remove_pid()
            return True
        time.sleep(0.2)
    # Force kill
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    remove_pid()
    return True


# ---------------------------------------------------------------------------
# Job execution
# ---------------------------------------------------------------------------

async def execute_job(job: dict[str, Any]) -> dict[str, Any]:
    """Run a single cron job and return a history entry."""
    name = job["name"]
    command = job["command"]
    cwd = Path(job.get("cwd") or ".").expanduser()
    started_at = datetime.now(timezone.utc)

    logger.info("Executing cron job %r: %s", name, command)
    try:
        process = await asyncio.create_subprocess_exec(
            "/bin/bash",
            "-lc",
            command,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=300,
        )
    except asyncio.TimeoutError:
        try:
            process.kill()
            await process.wait()
        except Exception:
            pass
        entry = {
            "name": name,
            "command": command,
            "started_at": started_at.isoformat(),
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "returncode": -1,
            "status": "timeout",
            "stdout": "",
            "stderr": "Job timed out after 300s",
        }
        mark_job_run(name, success=False)
        append_history(entry)
        return entry
    except Exception as exc:
        entry = {
            "name": name,
            "command": command,
            "started_at": started_at.isoformat(),
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "returncode": -1,
            "status": "error",
            "stdout": "",
            "stderr": str(exc),
        }
        mark_job_run(name, success=False)
        append_history(entry)
        return entry

    success = process.returncode == 0
    entry = {
        "name": name,
        "command": command,
        "started_at": started_at.isoformat(),
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "returncode": process.returncode,
        "status": "success" if success else "failed",
        "stdout": (stdout.decode("utf-8", errors="replace")[-2000:] if stdout else ""),
        "stderr": (stderr.decode("utf-8", errors="replace")[-2000:] if stderr else ""),
    }
    mark_job_run(name, success=success)
    append_history(entry)
    logger.info("Job %r finished: %s (rc=%s)", name, entry["status"], process.returncode)
    return entry


# ---------------------------------------------------------------------------
# Scheduler loop
# ---------------------------------------------------------------------------

def _jobs_due(jobs: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """Return jobs whose next_run is at or before *now*."""
    due: list[dict[str, Any]] = []
    for job in jobs:
        if not job.get("enabled", True):
            continue
        schedule = job.get("schedule", "")
        if not validate_cron_expression(schedule):
            continue
        next_run_str = job.get("next_run")
        if not next_run_str:
            continue
        try:
            next_run = datetime.fromisoformat(next_run_str)
            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if next_run <= now:
            due.append(job)
    return due


async def run_scheduler_loop(*, once: bool = False) -> None:
    """Main scheduler loop.  Runs until SIGTERM or *once* is True (test mode)."""
    shutdown = asyncio.Event()

    def _on_signal() -> None:
        logger.info("Received shutdown signal")
        shutdown.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _on_signal)

    write_pid()
    logger.info("Cron scheduler started (pid=%d, tick=%ds)", os.getpid(), TICK_INTERVAL_SECONDS)

    try:
        while not shutdown.is_set():
            now = datetime.now(timezone.utc)
            jobs = load_cron_jobs()
            due = _jobs_due(jobs, now)

            if due:
                logger.info("Tick: %d job(s) due", len(due))
                # Execute due jobs concurrently
                results = await asyncio.gather(
                    *(execute_job(job) for job in due), return_exceptions=True
                )
                for result in results:
                    if isinstance(result, BaseException):
                        logger.error("Unexpected error executing cron job: %s", result)

            if once:
                break

            try:
                await asyncio.wait_for(shutdown.wait(), timeout=TICK_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
    finally:
        remove_pid()
        logger.info("Cron scheduler stopped")


# ---------------------------------------------------------------------------
# Daemon entry point (spawned by ``oh cron start``)
# ---------------------------------------------------------------------------

def _run_daemon() -> None:
    """Entry point for the scheduler subprocess."""
    log_file = get_logs_dir() / "cron_scheduler.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_file),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    asyncio.run(run_scheduler_loop())


def start_daemon() -> int:
    """Fork and start the scheduler daemon.  Returns the child PID."""
    existing = read_pid()
    if existing is not None:
        raise RuntimeError(f"Scheduler already running (pid={existing})")

    pid = os.fork()
    if pid > 0:
        # Parent — wait a moment for the child to write its PID file
        time.sleep(0.3)
        return pid

    # Child — detach
    os.setsid()
    # Redirect stdio
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    os.close(devnull)

    _run_daemon()
    sys.exit(0)


def scheduler_status() -> dict[str, Any]:
    """Return a status dict about the scheduler."""
    pid = read_pid()
    log_path = get_logs_dir() / "cron_scheduler.log"
    jobs = load_cron_jobs()
    enabled = [j for j in jobs if j.get("enabled", True)]
    return {
        "running": pid is not None,
        "pid": pid,
        "total_jobs": len(jobs),
        "enabled_jobs": len(enabled),
        "log_file": str(log_path),
        "history_file": str(get_history_path()),
    }
