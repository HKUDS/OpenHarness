"""Tests for background task management."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from openharness.tasks.manager import BackgroundTaskManager, _encode_task_worker_payload


@pytest.mark.asyncio
async def test_create_shell_task_and_read_output(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()

    task = await manager.create_shell_task(
        command="printf 'hello task'",
        description="hello",
        cwd=tmp_path,
    )

    await asyncio.wait_for(manager._waiters[task.id], timeout=5)  # type: ignore[attr-defined]
    updated = manager.get_task(task.id)
    assert updated is not None
    assert updated.status == "completed"
    assert "hello task" in manager.read_task_output(task.id)


@pytest.mark.asyncio
async def test_create_agent_task_with_command_override_and_write(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()

    task = await manager.create_agent_task(
        prompt="first",
        description="agent",
        cwd=tmp_path,
        command="while read line; do echo \"got:$line\"; break; done",
    )

    await asyncio.wait_for(manager._waiters[task.id], timeout=5)  # type: ignore[attr-defined]
    assert "got:first" in manager.read_task_output(task.id)


@pytest.mark.asyncio
async def test_create_agent_task_preserves_multiline_prompt(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()

    task = await manager.create_agent_task(
        prompt="line 1\nline 2\nline 3",
        description="agent",
        cwd=tmp_path,
        command=(
            "python -u -c \"import sys, json; "
            "print(json.loads(sys.stdin.readline())['text'].replace(chr(10), '|'))\""
        ),
    )

    await asyncio.wait_for(manager._waiters[task.id], timeout=5)  # type: ignore[attr-defined]
    assert "line 1|line 2|line 3" in manager.read_task_output(task.id)


@pytest.mark.asyncio
async def test_write_to_stopped_agent_task_restarts_process(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()

    task = await manager.create_agent_task(
        prompt="ready",
        description="agent",
        cwd=tmp_path,
        command="while read line; do echo \"got:$line\"; break; done",
    )
    await asyncio.wait_for(manager._waiters[task.id], timeout=5)  # type: ignore[attr-defined]

    await manager.write_to_task(task.id, "follow-up")
    await asyncio.wait_for(manager._waiters[task.id], timeout=5)  # type: ignore[attr-defined]

    output = manager.read_task_output(task.id)
    assert "got:ready" in output
    assert "[OpenHarness] Agent task restarted; prior interactive context was not preserved." in output
    assert "got:follow-up" in output
    updated = manager.get_task(task.id)
    assert updated is not None
    assert updated.metadata["restart_count"] == "1"
    assert updated.metadata["status_note"] == "Task restarted; prior interactive context was not preserved."


@pytest.mark.asyncio
async def test_create_shell_task_stores_env_on_record(tmp_path: Path, monkeypatch):
    """``env=`` passed to ``create_shell_task`` must land on the
    ``TaskRecord.env`` field so ``_start_process`` can forward it to the
    subprocess. Plumbing this dict instead of baking ``KEY=val`` into the
    command string is the fix for #230."""
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()

    task = await manager.create_shell_task(
        command="printf 'noop'",
        description="env test",
        cwd=tmp_path,
        env={"MY_OH_TEST_VAR": "hello-230"},
    )
    await asyncio.wait_for(manager._waiters[task.id], timeout=5)  # type: ignore[attr-defined]

    stored = manager.get_task(task.id)
    assert stored is not None
    assert stored.env == {"MY_OH_TEST_VAR": "hello-230"}


@pytest.mark.asyncio
async def test_create_shell_task_argv_path_bypasses_shell(tmp_path: Path, monkeypatch):
    """The argv path runs the executable directly via
    ``asyncio.create_subprocess_exec(*argv)`` with no shell. This is the
    fix for #230: bash on Windows cannot exec Windows-pathed binaries
    when launched via ``create_subprocess_exec``, so teammate spawn must
    not route through a shell."""
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()

    import sys
    task = await manager.create_shell_task(
        argv=[sys.executable, "-c", "print('argv-route-ok')"],
        description="argv direct exec",
        cwd=tmp_path,
    )
    await asyncio.wait_for(manager._waiters[task.id], timeout=10)  # type: ignore[attr-defined]

    output = manager.read_task_output(task.id)
    assert "argv-route-ok" in output
    stored = manager.get_task(task.id)
    assert stored is not None
    assert stored.argv is not None
    assert stored.command is None


@pytest.mark.asyncio
async def test_create_shell_task_rejects_both_command_and_argv(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()
    with pytest.raises(ValueError, match="only one"):
        await manager.create_shell_task(
            command="printf hi",
            argv=["echo", "hi"],
            description="both",
            cwd=tmp_path,
        )


@pytest.mark.asyncio
async def test_create_shell_task_rejects_neither_command_nor_argv(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()
    with pytest.raises(ValueError, match="either command or argv"):
        await manager.create_shell_task(
            description="empty",
            cwd=tmp_path,
        )


@pytest.mark.asyncio
async def test_start_process_forwards_env_to_subprocess(tmp_path: Path, monkeypatch):
    """End-to-end: env vars passed via ``create_shell_task(env=...)`` must be
    visible to the spawned subprocess. The subprocess prints the value, and
    we read it back from the task output."""
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()

    task = await manager.create_shell_task(
        command='printf "value=%s" "$MY_OH_TEST_VAR"',
        description="env passthrough",
        cwd=tmp_path,
        env={"MY_OH_TEST_VAR": "spawn-230"},
    )
    await asyncio.wait_for(manager._waiters[task.id], timeout=5)  # type: ignore[attr-defined]

    output = manager.read_task_output(task.id)
    assert "value=spawn-230" in output


def test_encode_task_worker_payload_wraps_multiline_text() -> None:
    payload = _encode_task_worker_payload("alpha\nbeta\n")
    assert json.loads(payload.decode("utf-8")) == {"text": "alpha\nbeta"}


def test_encode_task_worker_payload_preserves_structured_messages() -> None:
    raw = '{"text":"follow up","from":"coordinator"}'
    payload = _encode_task_worker_payload(raw)
    assert payload.decode("utf-8") == raw + "\n"


@pytest.mark.asyncio
async def test_stop_task(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()

    task = await manager.create_shell_task(
        command="sleep 30",
        description="sleeper",
        cwd=tmp_path,
    )
    await manager.stop_task(task.id)
    updated = manager.get_task(task.id)
    assert updated is not None
    assert updated.status == "killed"


@pytest.mark.asyncio
async def test_completion_listener_fires_when_task_finishes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()
    seen: list[tuple[str, str, int | None]] = []
    done = asyncio.Event()

    async def _listener(task):
        seen.append((task.id, task.status, task.return_code))
        done.set()

    manager.register_completion_listener(_listener)

    task = await manager.create_shell_task(
        command="printf 'done'",
        description="listener",
        cwd=tmp_path,
    )

    await asyncio.wait_for(done.wait(), timeout=5)

    assert seen == [(task.id, "completed", 0)]
