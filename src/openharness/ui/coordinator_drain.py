"""Coordinator-mode helpers for draining background agent tasks between turns.

When coordinator mode dispatches workers via the ``agent`` tool, the system
prompt promises that worker results arrive as user-role ``<task-notification>``
messages between coordinator turns. The harness has to honor that contract by
polling the task manager for completion, formatting the notification, and
submitting it as a follow-up to the coordinator. These helpers implement that
behavior independently of the UI host so both print mode and interactive
backends can share the same logic.
"""

from __future__ import annotations

import asyncio

from openharness.coordinator.coordinator_mode import (
    TaskNotification,
    format_task_notification,
)
from openharness.engine.query import MaxTurnsExceeded
from openharness.prompts.context import build_runtime_system_prompt
from openharness.tasks.manager import get_task_manager


_TERMINAL_TASK_STATUSES = frozenset({"completed", "failed", "killed"})


def _async_agent_task_entries(tool_metadata: dict[str, object] | None) -> list[dict[str, object]]:
    if not isinstance(tool_metadata, dict):
        return []
    value = tool_metadata.get("async_agent_tasks")
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def pending_async_agent_entries(tool_metadata: dict[str, object] | None) -> list[dict[str, object]]:
    pending: list[dict[str, object]] = []
    for entry in _async_agent_task_entries(tool_metadata):
        task_id = str(entry.get("task_id") or "").strip()
        if not task_id:
            continue
        if bool(entry.get("notification_sent")):
            continue
        pending.append(entry)
    return pending


def _build_async_task_summary(
    entry: dict[str, object], *, task_status: str, return_code: int | None
) -> str:
    description = str(entry.get("description") or entry.get("agent_id") or "background task").strip()
    if task_status == "completed":
        return f'Agent "{description}" completed'
    if task_status == "killed":
        return f'Agent "{description}" was stopped'
    if return_code is not None:
        return f'Agent "{description}" failed with exit code {return_code}'
    return f'Agent "{description}" failed'


async def wait_for_completed_async_agent_entries(
    tool_metadata: dict[str, object] | None,
    *,
    poll_interval_seconds: float = 0.1,
) -> list[dict[str, object]]:
    manager = get_task_manager()
    while True:
        pending = pending_async_agent_entries(tool_metadata)
        if not pending:
            return []
        completed: list[dict[str, object]] = []
        for entry in pending:
            task_id = str(entry.get("task_id") or "").strip()
            task = manager.get_task(task_id)
            if task is None:
                entry["notification_sent"] = True
                entry["status"] = "missing"
                continue
            entry["status"] = task.status
            if task.status in _TERMINAL_TASK_STATUSES:
                entry["return_code"] = task.return_code
                completed.append(entry)
        if completed:
            return completed
        await asyncio.sleep(poll_interval_seconds)


def format_completed_task_notifications(completed: list[dict[str, object]]) -> str:
    manager = get_task_manager()
    notifications: list[str] = []
    for entry in completed:
        task_id = str(entry.get("task_id") or "").strip()
        agent_id = str(entry.get("agent_id") or task_id).strip()
        task = manager.get_task(task_id)
        if task is None:
            continue
        output = manager.read_task_output(task_id, max_bytes=8000).strip()
        notifications.append(
            format_task_notification(
                TaskNotification(
                    task_id=agent_id,
                    status=task.status,
                    summary=_build_async_task_summary(
                        entry,
                        task_status=task.status,
                        return_code=task.return_code,
                    ),
                    result=output or None,
                )
            )
        )
        entry["notification_sent"] = True
        entry["notified_status"] = task.status
    return "\n\n".join(notifications)


async def submit_follow_up(
    bundle,
    message: str,
    *,
    prompt_seed: str,
    print_system,
    render_event,
) -> None:
    from openharness.ui.runtime import _format_pending_tool_results

    settings = bundle.current_settings()
    if bundle.enforce_max_turns:
        bundle.engine.set_max_turns(settings.max_turns)
    system_prompt = build_runtime_system_prompt(
        settings,
        cwd=bundle.cwd,
        latest_user_prompt=prompt_seed,
        extra_skill_dirs=bundle.extra_skill_dirs,
        extra_plugin_roots=bundle.extra_plugin_roots,
        include_project_memory=getattr(bundle, "include_project_memory", True),
    )
    bundle.engine.set_system_prompt(system_prompt)
    try:
        async for event in bundle.engine.submit_message(message):
            await render_event(event)
    except MaxTurnsExceeded as exc:
        await print_system(f"Stopped after {exc.max_turns} turns (max_turns).")
        pending = _format_pending_tool_results(bundle.engine.messages)
        if pending:
            await print_system(pending)
    bundle.session_backend.save_snapshot(
        cwd=bundle.cwd,
        model=settings.model,
        system_prompt=system_prompt,
        messages=bundle.engine.messages,
        usage=bundle.engine.total_usage,
        session_id=bundle.session_id,
        tool_metadata=bundle.engine.tool_metadata,
    )


async def drain_coordinator_async_agents(
    bundle,
    *,
    prompt_seed: str,
    print_system,
    render_event,
    announce_waiting: bool = True,
) -> None:
    """Block until pending async-agent tasks finish, then submit notifications.

    Submits one follow-up turn per batch of completed workers so the coordinator
    sees ``<task-notification>`` envelopes between its own turns, matching the
    contract documented in the coordinator system prompt.

    Returns immediately when there are no pending async-agent entries.
    """
    engine = getattr(bundle, "engine", None)
    if engine is None:
        return
    while True:
        pending = pending_async_agent_entries(getattr(engine, "tool_metadata", None))
        if not pending:
            return
        if announce_waiting:
            await print_system(
                f"Waiting for {len(pending)} background agent task(s) to finish..."
            )
        completed = await wait_for_completed_async_agent_entries(
            getattr(engine, "tool_metadata", None)
        )
        notification_payload = format_completed_task_notifications(completed)
        if not notification_payload.strip():
            return
        await submit_follow_up(
            bundle,
            notification_payload,
            prompt_seed=prompt_seed,
            print_system=print_system,
            render_event=render_event,
        )
