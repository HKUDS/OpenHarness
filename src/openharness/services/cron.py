"""Local cron-style registry helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from croniter import croniter

from openharness.config.paths import get_cron_registry_path


def load_cron_jobs() -> list[dict[str, Any]]:
    """Load stored cron jobs."""
    path = get_cron_registry_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def save_cron_jobs(jobs: list[dict[str, Any]]) -> None:
    """Persist cron jobs to disk."""
    path = get_cron_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jobs, indent=2) + "\n", encoding="utf-8")


def validate_cron_expression(expression: str) -> bool:
    """Return True if the expression is a valid cron schedule."""
    return croniter.is_valid(expression)


def next_run_time(expression: str, base: datetime | None = None) -> datetime:
    """Return the next run time for a cron expression."""
    base = base or datetime.now(timezone.utc)
    return croniter(expression, base).get_next(datetime)


def upsert_cron_job(job: dict[str, Any]) -> None:
    """Insert or replace one cron job.

    Automatically sets ``enabled`` to True and computes ``next_run`` when the
    schedule is a valid cron expression.
    """
    job.setdefault("enabled", True)
    job.setdefault("created_at", datetime.now(timezone.utc).isoformat())

    schedule = job.get("schedule", "")
    if validate_cron_expression(schedule):
        job["next_run"] = next_run_time(schedule).isoformat()

    jobs = [existing for existing in load_cron_jobs() if existing.get("name") != job.get("name")]
    jobs.append(job)
    jobs.sort(key=lambda item: str(item.get("name", "")))
    save_cron_jobs(jobs)


def delete_cron_job(name: str) -> bool:
    """Delete one cron job by name."""
    jobs = load_cron_jobs()
    filtered = [job for job in jobs if job.get("name") != name]
    if len(filtered) == len(jobs):
        return False
    save_cron_jobs(filtered)
    return True


def get_cron_job(name: str) -> dict[str, Any] | None:
    """Return one cron job by name."""
    for job in load_cron_jobs():
        if job.get("name") == name:
            return job
    return None


def set_job_enabled(name: str, enabled: bool) -> bool:
    """Enable or disable a cron job. Returns False if job not found."""
    jobs = load_cron_jobs()
    for job in jobs:
        if job.get("name") == name:
            job["enabled"] = enabled
            save_cron_jobs(jobs)
            return True
    return False


def mark_job_run(name: str, *, success: bool) -> None:
    """Update last_run and recompute next_run after a job executes."""
    jobs = load_cron_jobs()
    now = datetime.now(timezone.utc)
    for job in jobs:
        if job.get("name") == name:
            job["last_run"] = now.isoformat()
            job["last_status"] = "success" if success else "failed"
            schedule = job.get("schedule", "")
            if validate_cron_expression(schedule):
                job["next_run"] = next_run_time(schedule, now).isoformat()
            save_cron_jobs(jobs)
            return
