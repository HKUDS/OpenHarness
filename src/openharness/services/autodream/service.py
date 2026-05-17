"""Auto-dream service."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from openharness.config.settings import Settings
from openharness.memory.paths import get_project_memory_dir
from openharness.memory.usage import find_stale_memory_candidates
from openharness.services.autodream.backup import create_memory_backup, diff_memory_dirs
from openharness.services.autodream.lock import (
    list_sessions_touched_since,
    read_last_consolidated_at,
    rollback_consolidation_lock,
    try_acquire_consolidation_lock,
)
from openharness.services.autodream.prompt import build_consolidation_prompt
from openharness.services.session_storage import get_project_session_dir
from openharness.tasks.manager import get_task_manager
from openharness.tasks.types import TaskRecord

SESSION_SCAN_INTERVAL_SECONDS = 10 * 60
_CHILD_ENV = "OPENHARNESS_AUTODREAM_CHILD"
_last_session_scan_at: dict[str, float] = {}
_listener_registered = False


def _enabled(settings: Settings) -> bool:
    return bool(settings.memory.enabled and settings.memory.auto_dream_enabled)


def _has_dream_signal(session_ids: list[str], *, force: bool) -> bool:
    """Return whether recent sessions are worth consolidating."""

    if force:
        return True
    return bool(session_ids)


def _memory_files_mtime_snapshot(memory_dir: Path) -> dict[str, float]:
    snapshot: dict[str, float] = {}
    for path in memory_dir.glob("*.md"):
        try:
            snapshot[path.name] = path.stat().st_mtime
        except OSError:
            continue
    return snapshot


def _files_changed_since(memory_dir: Path, before: dict[str, float]) -> list[str]:
    changed: list[str] = []
    for path in sorted(memory_dir.glob("*.md")):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if before.get(path.name) != mtime:
            changed.append(path.name)
    return changed


def _ensure_listener_registered() -> None:
    global _listener_registered
    if _listener_registered:
        return

    async def _listener(task: TaskRecord) -> None:
        if task.type != "dream":
            return
        prior_raw = task.metadata.get("prior_mtime", "")
        memory_dir = task.metadata.get("memory_dir") or None
        if not prior_raw:
            return
        try:
            prior_mtime = float(prior_raw)
        except ValueError:
            return
        if task.status in {"failed", "killed"} or task.metadata.get("preview") == "true":
            rollback_consolidation_lock(task.cwd, prior_mtime, memory_dir=memory_dir)

    get_task_manager().register_completion_listener(_listener)
    _listener_registered = True


def _resolve_memory_dir(cwd: str | Path, memory_dir: str | Path | None) -> Path:
    return Path(memory_dir).expanduser().resolve() if memory_dir is not None else get_project_memory_dir(cwd)


def _resolve_session_dir(cwd: str | Path, session_dir: str | Path | None) -> Path:
    return Path(session_dir).expanduser().resolve() if session_dir is not None else get_project_session_dir(cwd)


async def start_dream_now(
    *,
    cwd: str | Path,
    settings: Settings,
    model: str | None = None,
    current_session_id: str | None = None,
    force: bool = False,
    memory_dir: str | Path | None = None,
    session_dir: str | Path | None = None,
    app_label: str = "openharness",
    runner_module: str = "openharness",
    preview: bool = False,
) -> TaskRecord | None:
    """Start a dream task immediately, optionally bypassing time/session gates."""

    if os.environ.get(_CHILD_ENV):
        return None
    if not settings.memory.enabled:
        return None

    cwd = Path(cwd).resolve()
    resolved_memory_dir = _resolve_memory_dir(cwd, memory_dir)
    resolved_session_dir = _resolve_session_dir(cwd, session_dir)
    last_at = read_last_consolidated_at(cwd, memory_dir=resolved_memory_dir)
    session_ids = list_sessions_touched_since(
        cwd,
        last_at,
        current_session_id=current_session_id,
        session_dir=resolved_session_dir,
    )
    if not force:
        hours_since = (time.time() - last_at) / 3600
        if hours_since < settings.memory.auto_dream_min_hours:
            return None
        if len(session_ids) < settings.memory.auto_dream_min_sessions:
            return None
    if not _has_dream_signal(session_ids, force=force):
        return None

    prior_mtime = try_acquire_consolidation_lock(cwd, memory_dir=resolved_memory_dir)
    if prior_mtime is None:
        return None

    _ensure_listener_registered()
    resolved_memory_dir.mkdir(parents=True, exist_ok=True)
    resolved_session_dir.mkdir(parents=True, exist_ok=True)
    before = _memory_files_mtime_snapshot(resolved_memory_dir)
    backup_dir = create_memory_backup(resolved_memory_dir, app_label=app_label) if not preview else None
    stale_candidates = find_stale_memory_candidates(cwd, memory_dir=resolved_memory_dir)
    stale_section = "\n".join(
        f"- {header.id or header.path.name}: {header.path.name} "
        f"(importance={header.importance}, updated_at={header.updated_at or 'unknown'})"
        for header in stale_candidates[:20]
    ) or "- (none)"
    extra = (
        f"Application context: `{app_label}`.\n"
        "Tool constraints for this run: only modify files under the memory directory. "
        "Use shell commands only for read-only inspection.\n\n"
        f"Sessions since last consolidation ({len(session_ids)}):\n"
        + "\n".join(f"- {session_id}" for session_id in session_ids)
        + "\n\nUsage-based stale candidates:\n"
        + stale_section
    )
    prompt = build_consolidation_prompt(resolved_memory_dir, resolved_session_dir, extra, preview=preview)
    src_root = Path(__file__).resolve().parents[3]
    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    env = {
        _CHILD_ENV: "1",
        "OPENHARNESS_AUTODREAM_MEMORY_DIR": str(resolved_memory_dir),
        "OPENHARNESS_CONFIG_DIR": str(Path.home() / ".openharness"),
        "OPENHARNESS_PROFILE": settings.active_profile,
        "PYTHONPATH": str(src_root) + ((os.pathsep + existing_pythonpath) if existing_pythonpath else ""),
    }
    try:
        argv = [
            sys.executable,
            "-m",
            runner_module,
        ]
        if runner_module == "openharness":
            argv.append("--dangerously-skip-permissions")
        if runner_module == "ohmo":
            workspace = resolved_memory_dir.parent
            argv.extend(["--workspace", str(workspace)])
            if settings.active_profile:
                argv.extend(["--profile", settings.active_profile])
        if model:
            argv.extend(["--model", model])
        if runner_module == "openharness" and settings.provider != "anthropic_claude":
            if settings.base_url:
                argv.extend(["--base-url", settings.base_url])
            if settings.api_format:
                argv.extend(["--api-format", settings.api_format])
        try:
            auth = settings.resolve_auth()
            if runner_module == "openharness" and auth.auth_kind == "api_key":
                argv.extend(["--api-key", auth.value])
            elif runner_module == "ohmo" and auth.auth_kind == "api_key":
                env["OPENHARNESS_API_KEY"] = auth.value
            elif auth.value:
                env["ANTHROPIC_AUTH_TOKEN"] = auth.value
                env.pop("ANTHROPIC_API_KEY", None)
                env.pop("OPENAI_API_KEY", None)
                env.pop("OPENHARNESS_API_KEY", None)
        except Exception:
            pass
        argv.extend(["--print", prompt])
        task = await get_task_manager().create_shell_task(
            description="dreaming",
            cwd=cwd,
            task_type="dream",
            env=env,
            argv=argv,
        )
        task.prompt = prompt
    except Exception:
        rollback_consolidation_lock(cwd, prior_mtime, memory_dir=resolved_memory_dir)
        raise

    task.metadata.update(
        {
            "phase": "starting",
            "sessions_reviewing": str(len(session_ids)),
            "prior_mtime": str(prior_mtime),
            "memory_dir": str(resolved_memory_dir),
            "session_dir": str(resolved_session_dir),
            "force": str(force).lower(),
            "app_label": app_label,
            "runner_module": runner_module,
            "preview": str(preview).lower(),
            "backup_dir": str(backup_dir or ""),
        }
    )

    async def _mark_changed_on_completion(done: TaskRecord) -> None:
        if done.id != task.id or done.status != "completed":
            return
        changed = _files_changed_since(resolved_memory_dir, before)
        if backup_dir is not None:
            diff = diff_memory_dirs(backup_dir, resolved_memory_dir)
            done.metadata["files_added"] = "\n".join(diff["added"])
            done.metadata["files_changed"] = "\n".join(diff["changed"])
            done.metadata["files_removed"] = "\n".join(diff["removed"])
        if changed:
            done.metadata["phase"] = "updating"
            done.metadata["files_touched"] = "\n".join(changed)

    get_task_manager().register_completion_listener(_mark_changed_on_completion)
    return task


async def execute_auto_dream(
    *,
    cwd: str | Path,
    settings: Settings,
    model: str | None = None,
    current_session_id: str | None = None,
    memory_dir: str | Path | None = None,
    session_dir: str | Path | None = None,
    app_label: str = "openharness",
    runner_module: str = "openharness",
    preview: bool = False,
) -> TaskRecord | None:
    """Run the cheap auto-dream gates and start a background dream when eligible."""

    if os.environ.get(_CHILD_ENV):
        return None
    if not _enabled(settings):
        return None

    cwd = Path(cwd).resolve()
    resolved_memory_dir = _resolve_memory_dir(cwd, memory_dir)
    resolved_session_dir = _resolve_session_dir(cwd, session_dir)
    last_at = read_last_consolidated_at(cwd, memory_dir=resolved_memory_dir)
    hours_since = (time.time() - last_at) / 3600
    if hours_since < settings.memory.auto_dream_min_hours:
        return None

    key = str(resolved_memory_dir)
    now = time.time()
    if now - _last_session_scan_at.get(key, 0) < SESSION_SCAN_INTERVAL_SECONDS:
        return None
    _last_session_scan_at[key] = now

    session_ids = list_sessions_touched_since(
        cwd,
        last_at,
        current_session_id=current_session_id,
        session_dir=resolved_session_dir,
    )
    if len(session_ids) < settings.memory.auto_dream_min_sessions:
        return None
    if not _has_dream_signal(session_ids, force=False):
        return None

    return await start_dream_now(
        cwd=cwd,
        settings=settings,
        model=model,
        current_session_id=current_session_id,
        force=False,
        memory_dir=resolved_memory_dir,
        session_dir=resolved_session_dir,
        app_label=app_label,
        runner_module=runner_module,
        preview=preview,
    )


def schedule_auto_dream(**kwargs: object) -> None:
    """Fire-and-forget auto-dream scheduling."""

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(execute_auto_dream(**kwargs))  # type: ignore[arg-type]
