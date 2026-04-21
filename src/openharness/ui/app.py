"""Interactive session entry points."""

from __future__ import annotations

import asyncio
import json
import sys

from openharness.coordinator.coordinator_mode import (
    TaskNotification,
    format_task_notification,
    is_coordinator_mode,
)
from openharness.engine.query import MaxTurnsExceeded
from openharness.prompts.context import build_runtime_system_prompt
from openharness.tasks.manager import get_task_manager

from openharness.api.client import SupportsStreamingMessages
from openharness.engine.stream_events import StreamEvent
from openharness.ui.backend_host import run_backend_host
from openharness.ui.react_launcher import launch_react_tui
from openharness.ui.runtime import build_runtime, close_runtime, handle_line, start_runtime


_TERMINAL_TASK_STATUSES = frozenset({"completed", "failed", "killed"})


def _decode_task_worker_line(raw: str) -> str:
    """Normalize one stdin line for the headless task worker.

    Task-manager driven agent workers receive either:
    - a plain text line (initial prompt or simple follow-up), or
    - a JSON object from ``send_message`` / teammate backends with a ``text`` field.
    """
    stripped = raw.strip()
    if not stripped:
        return ""
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    if isinstance(payload, dict):
        text = payload.get("text")
        if isinstance(text, str):
            return text.strip()
    return stripped


def _async_agent_task_entries(tool_metadata: dict[str, object] | None) -> list[dict[str, object]]:
    if not isinstance(tool_metadata, dict):
        return []
    value = tool_metadata.get("async_agent_tasks")
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def _pending_async_agent_entries(tool_metadata: dict[str, object] | None) -> list[dict[str, object]]:
    pending: list[dict[str, object]] = []
    for entry in _async_agent_task_entries(tool_metadata):
        task_id = str(entry.get("task_id") or "").strip()
        if not task_id:
            continue
        if bool(entry.get("notification_sent")):
            continue
        pending.append(entry)
    return pending


def _build_async_task_summary(entry: dict[str, object], *, task_status: str, return_code: int | None) -> str:
    description = str(entry.get("description") or entry.get("agent_id") or "background task").strip()
    if task_status == "completed":
        return f'Agent "{description}" completed'
    if task_status == "killed":
        return f'Agent "{description}" was stopped'
    if return_code is not None:
        return f'Agent "{description}" failed with exit code {return_code}'
    return f'Agent "{description}" failed'


async def _wait_for_completed_async_agent_entries(
    tool_metadata: dict[str, object] | None,
    *,
    poll_interval_seconds: float = 0.1,
) -> list[dict[str, object]]:
    manager = get_task_manager()
    while True:
        pending = _pending_async_agent_entries(tool_metadata)
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


def _format_completed_task_notifications(completed: list[dict[str, object]]) -> str:
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


async def _submit_print_follow_up(
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


async def _drain_coordinator_async_agents(
    bundle,
    *,
    prompt_seed: str,
    output_format: str,
    print_system,
    render_event,
) -> None:
    engine = getattr(bundle, "engine", None)
    if engine is None:
        return
    while True:
        pending = _pending_async_agent_entries(getattr(engine, "tool_metadata", None))
        if not pending:
            return
        if output_format == "text":
            await print_system(
                f"Waiting for {len(pending)} background agent task(s) to finish..."
            )
        completed = await _wait_for_completed_async_agent_entries(getattr(engine, "tool_metadata", None))
        notification_payload = _format_completed_task_notifications(completed)
        if not notification_payload.strip():
            return
        await _submit_print_follow_up(
            bundle,
            notification_payload,
            prompt_seed=prompt_seed,
            print_system=print_system,
            render_event=render_event,
        )


async def run_repl(
    *,
    prompt: str | None = None,
    cwd: str | None = None,
    model: str | None = None,
    max_turns: int | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    api_key: str | None = None,
    api_format: str | None = None,
    api_client: SupportsStreamingMessages | None = None,
    backend_only: bool = False,
    restore_messages: list[dict] | None = None,
    restore_tool_metadata: dict[str, object] | None = None,
    permission_mode: str | None = None,
) -> None:
    """Run the default OpenHarness interactive application (React TUI)."""
    if backend_only:
        await run_backend_host(
            cwd=cwd,
            model=model,
            max_turns=max_turns,
            base_url=base_url,
            system_prompt=system_prompt,
            api_key=api_key,
            api_format=api_format,
            api_client=api_client,
            restore_messages=restore_messages,
            restore_tool_metadata=restore_tool_metadata,
            enforce_max_turns=max_turns is not None,
            permission_mode=permission_mode,
        )
        return

    exit_code = await launch_react_tui(
        prompt=prompt,
        cwd=cwd,
        model=model,
        max_turns=max_turns,
        base_url=base_url,
        system_prompt=system_prompt,
        api_key=api_key,
        api_format=api_format,
        permission_mode=permission_mode,
    )
    if exit_code != 0:
        raise SystemExit(exit_code)


async def run_task_worker(
    *,
    cwd: str | None = None,
    model: str | None = None,
    max_turns: int | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    api_key: str | None = None,
    api_format: str | None = None,
    api_client: SupportsStreamingMessages | None = None,
    permission_mode: str | None = None,
) -> None:
    """Run a stdin-driven headless worker for background agent tasks.

    This mode exists for subprocess teammates and other task-manager managed
    agent processes. It intentionally avoids the React TUI / Ink path so it
    can run without a controlling TTY.
    """

    async def _noop_permission(_tool_name: str, _reason: str) -> bool:
        return True

    async def _noop_ask(_question: str) -> str:
        return ""

    async def _print_system(message: str) -> None:
        print(message, flush=True)

    async def _render_event(event: StreamEvent) -> None:
        from openharness.engine.stream_events import AssistantTextDelta, AssistantTurnComplete, ErrorEvent, StatusEvent

        if isinstance(event, AssistantTextDelta):
            sys.stdout.write(event.text)
            sys.stdout.flush()
        elif isinstance(event, AssistantTurnComplete):
            sys.stdout.write("\n")
            sys.stdout.flush()
        elif isinstance(event, ErrorEvent):
            print(event.message, flush=True)
        elif isinstance(event, StatusEvent) and event.message:
            print(event.message, flush=True)

    async def _clear_output() -> None:
        return None

    bundle = await build_runtime(
        cwd=cwd,
        model=model,
        max_turns=max_turns,
        base_url=base_url,
        system_prompt=system_prompt,
        api_key=api_key,
        api_format=api_format,
        api_client=api_client,
        permission_prompt=_noop_permission,
        ask_user_prompt=_noop_ask,
        enforce_max_turns=max_turns is not None,
        permission_mode=permission_mode,
    )
    await start_runtime(bundle)
    try:
        while True:
            raw = await asyncio.to_thread(sys.stdin.readline)
            if raw == "":
                break
            line = _decode_task_worker_line(raw)
            if not line:
                continue
            await handle_line(
                bundle,
                line,
                print_system=_print_system,
                render_event=_render_event,
                clear_output=_clear_output,
            )
            # Background agent tasks are one-shot workers. If the coordinator
            # needs to send a follow-up later, BackgroundTaskManager already
            # knows how to restart the task and write the next stdin payload.
            break
    finally:
        await close_runtime(bundle)


async def run_print_mode(
    *,
    prompt: str,
    output_format: str = "text",
    cwd: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    append_system_prompt: str | None = None,
    api_key: str | None = None,
    api_format: str | None = None,
    api_client: SupportsStreamingMessages | None = None,
    permission_mode: str | None = None,
    max_turns: int | None = None,
) -> None:
    """Non-interactive mode: submit prompt, stream output, exit."""
    from openharness.engine.stream_events import (
        AssistantTextDelta,
        AssistantTurnComplete,
        CompactProgressEvent,
        ErrorEvent,
        StatusEvent,
        ToolExecutionCompleted,
        ToolExecutionStarted,
    )

    async def _noop_permission(tool_name: str, reason: str) -> bool:
        return True

    async def _noop_ask(question: str) -> str:
        return ""

    bundle = await build_runtime(
        prompt=prompt,
        cwd=cwd,
        model=model,
        max_turns=max_turns,
        base_url=base_url,
        system_prompt=system_prompt,
        api_key=api_key,
        api_format=api_format,
        enforce_max_turns=True,
        api_client=api_client,
        permission_prompt=_noop_permission,
        ask_user_prompt=_noop_ask,
    )
    await start_runtime(bundle)

    collected_text = ""
    events_list: list[dict] = []

    try:
        async def _print_system(message: str) -> None:
            nonlocal collected_text
            if output_format == "text":
                print(message, file=sys.stderr)
            elif output_format == "stream-json":
                obj = {"type": "system", "message": message}
                print(json.dumps(obj), flush=True)
                events_list.append(obj)

        async def _render_event(event: StreamEvent) -> None:
            nonlocal collected_text
            if isinstance(event, AssistantTextDelta):
                collected_text += event.text
                if output_format == "text":
                    sys.stdout.write(event.text)
                    sys.stdout.flush()
                elif output_format == "stream-json":
                    obj = {"type": "assistant_delta", "text": event.text}
                    print(json.dumps(obj), flush=True)
                    events_list.append(obj)
            elif isinstance(event, AssistantTurnComplete):
                if output_format == "text":
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                elif output_format == "stream-json":
                    obj = {"type": "assistant_complete", "text": event.message.text.strip()}
                    print(json.dumps(obj), flush=True)
                    events_list.append(obj)
            elif isinstance(event, ToolExecutionStarted):
                if output_format == "stream-json":
                    obj = {"type": "tool_started", "tool_name": event.tool_name, "tool_input": event.tool_input}
                    print(json.dumps(obj), flush=True)
                    events_list.append(obj)
            elif isinstance(event, ToolExecutionCompleted):
                if output_format == "stream-json":
                    obj = {"type": "tool_completed", "tool_name": event.tool_name, "output": event.output, "is_error": event.is_error}
                    print(json.dumps(obj), flush=True)
                    events_list.append(obj)
            elif isinstance(event, ErrorEvent):
                if output_format == "text":
                    print(event.message, file=sys.stderr)
                elif output_format == "stream-json":
                    obj = {"type": "error", "message": event.message, "recoverable": event.recoverable}
                    print(json.dumps(obj), flush=True)
                    events_list.append(obj)
            elif isinstance(event, CompactProgressEvent):
                if output_format == "text" and event.message:
                    print(event.message, file=sys.stderr)
                elif output_format == "stream-json":
                    obj = {
                        "type": "compact_progress",
                        "phase": event.phase,
                        "trigger": event.trigger,
                        "attempt": event.attempt,
                        "message": event.message,
                    }
                    print(json.dumps(obj), flush=True)
                    events_list.append(obj)
            elif isinstance(event, StatusEvent):
                if output_format == "text":
                    print(event.message, file=sys.stderr)
                elif output_format == "stream-json":
                    obj = {"type": "status", "message": event.message}
                    print(json.dumps(obj), flush=True)
                    events_list.append(obj)

        async def _clear_output() -> None:
            pass

        await handle_line(
            bundle,
            prompt,
            print_system=_print_system,
            render_event=_render_event,
            clear_output=_clear_output,
        )
        if is_coordinator_mode():
            await _drain_coordinator_async_agents(
                bundle,
                prompt_seed=prompt,
                output_format=output_format,
                print_system=_print_system,
                render_event=_render_event,
            )

        if output_format == "json":
            result = {"type": "result", "text": collected_text.strip()}
            print(json.dumps(result))
    finally:
        await close_runtime(bundle)
