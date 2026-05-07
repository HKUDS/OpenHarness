"""Path resolution for OpenHarness configuration and data directories.

Follows XDG-like conventions with ~/.openharness/ as the default base directory.
"""

from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_BASE_DIR = ".openharness"
_CONFIG_FILE_NAME = "settings.json"


def get_config_dir() -> Path:
    """Return the configuration directory, creating it if needed.

    Resolution order:
    1. OPENHARNESS_CONFIG_DIR environment variable
    2. ~/.openharness/
    """
    env_dir = os.environ.get("OPENHARNESS_CONFIG_DIR")
    if env_dir:
        config_dir = Path(env_dir)
    else:
        config_dir = Path.home() / _DEFAULT_BASE_DIR

    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_file_path() -> Path:
    """Return the path to the main settings file (~/.openharness/settings.json)."""
    return get_config_dir() / _CONFIG_FILE_NAME


def get_data_dir() -> Path:
    """Return the data directory for caches, history, etc.

    Resolution order:
    1. OPENHARNESS_DATA_DIR environment variable
    2. ~/.openharness/data/
    """
    env_dir = os.environ.get("OPENHARNESS_DATA_DIR")
    if env_dir:
        data_dir = Path(env_dir)
    else:
        data_dir = get_config_dir() / "data"

    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_logs_dir() -> Path:
    """Return the logs directory.

    Resolution order:
    1. OPENHARNESS_LOGS_DIR environment variable
    2. ~/.openharness/logs/
    """
    env_dir = os.environ.get("OPENHARNESS_LOGS_DIR")
    if env_dir:
        logs_dir = Path(env_dir)
    else:
        logs_dir = get_config_dir() / "logs"

    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_sessions_dir() -> Path:
    """Return the session storage directory."""
    sessions_dir = get_data_dir() / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return sessions_dir


def get_tasks_dir() -> Path:
    """Return the background task output directory."""
    tasks_dir = get_data_dir() / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    return tasks_dir


def get_feedback_dir() -> Path:
    """Return the feedback storage directory."""
    feedback_dir = get_data_dir() / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    return feedback_dir


def get_feedback_log_path() -> Path:
    """Return the feedback log file path."""
    return get_feedback_dir() / "feedback.log"


def get_cron_registry_path() -> Path:
    """Return the cron registry file path."""
    return get_data_dir() / "cron_jobs.json"


def get_project_config_dir(cwd: str | Path) -> Path:
    """Return the per-project .openharness directory."""
    project_dir = Path(cwd).resolve() / ".openharness"
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


def get_project_issue_file(cwd: str | Path) -> Path:
    """Return the per-project issue context file."""
    return get_project_config_dir(cwd) / "issue.md"


def get_project_pr_comments_file(cwd: str | Path) -> Path:
    """Return the per-project PR comments context file."""
    return get_project_config_dir(cwd) / "pr_comments.md"


def get_project_autopilot_dir(cwd: str | Path) -> Path:
    """Return the per-project autopilot state directory."""
    autopilot_dir = get_project_config_dir(cwd) / "autopilot"
    autopilot_dir.mkdir(parents=True, exist_ok=True)
    return autopilot_dir


def get_project_autopilot_registry_path(cwd: str | Path) -> Path:
    """Return the autopilot task registry path."""
    return get_project_autopilot_dir(cwd) / "registry.json"


def get_project_repo_journal_path(cwd: str | Path) -> Path:
    """Return the append-only repo journal path."""
    return get_project_autopilot_dir(cwd) / "repo_journal.jsonl"


def get_project_active_repo_context_path(cwd: str | Path) -> Path:
    """Return the synthesized active repo context path."""
    return get_project_autopilot_dir(cwd) / "active_repo_context.md"


def get_project_autopilot_policy_path(cwd: str | Path) -> Path:
    """Return the autopilot policy path."""
    return get_project_autopilot_dir(cwd) / "autopilot_policy.yaml"


def get_project_verification_policy_path(cwd: str | Path) -> Path:
    """Return the verification policy path."""
    return get_project_autopilot_dir(cwd) / "verification_policy.yaml"


def get_project_release_policy_path(cwd: str | Path) -> Path:
    """Return the release policy path."""
    return get_project_autopilot_dir(cwd) / "release_policy.yaml"


def get_project_autopilot_runs_dir(cwd: str | Path) -> Path:
    """Return the autopilot run artifacts directory."""
    runs_dir = get_project_autopilot_dir(cwd) / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    return runs_dir
