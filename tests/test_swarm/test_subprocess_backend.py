"""Tests for subprocess teammate spawning."""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.tasks.manager import BackgroundTaskManager
from openharness.tasks.types import TaskRecord
from openharness.swarm.subprocess_backend import SubprocessBackend
from openharness.swarm.types import TeammateSpawnConfig


@pytest.mark.asyncio
async def test_subprocess_backend_forwards_system_prompt_in_command(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    async def _fake_create_agent_task(self, **kwargs):
        captured.update(kwargs)
        return TaskRecord(
            id="task_123",
            type="local_agent",
            status="running",
            description=str(kwargs["description"]),
            cwd=str(kwargs["cwd"]),
            output_file=tmp_path / "task_123.log",
            command=str(kwargs["command"]),
        )

    monkeypatch.setattr(BackgroundTaskManager, "create_agent_task", _fake_create_agent_task)
    monkeypatch.setattr("openharness.swarm.subprocess_backend.get_teammate_command", lambda: "/usr/bin/python3")
    monkeypatch.setattr("openharness.swarm.subprocess_backend.build_inherited_env_vars", lambda: {})

    backend = SubprocessBackend()
    config = TeammateSpawnConfig(
        name="reviewer",
        team="default",
        prompt="Review the code changes.",
        cwd=str(tmp_path),
        parent_session_id="sess-001",
        system_prompt="You are a careful code reviewer.",
        task_type="local_agent",
    )

    result = await backend.spawn(config)

    assert result.success is True
    command = str(captured["command"])
    assert "--system-prompt" in command
    assert "You are a careful code reviewer." in command


@pytest.mark.asyncio
async def test_subprocess_backend_forwards_append_system_prompt_mode(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    async def _fake_create_agent_task(self, **kwargs):
        captured.update(kwargs)
        return TaskRecord(
            id="task_234",
            type="local_agent",
            status="running",
            description=str(kwargs["description"]),
            cwd=str(kwargs["cwd"]),
            output_file=tmp_path / "task_234.log",
            command=str(kwargs["command"]),
        )

    monkeypatch.setattr(BackgroundTaskManager, "create_agent_task", _fake_create_agent_task)
    monkeypatch.setattr("openharness.swarm.subprocess_backend.get_teammate_command", lambda: "/usr/bin/python3")
    monkeypatch.setattr("openharness.swarm.subprocess_backend.build_inherited_env_vars", lambda: {})

    backend = SubprocessBackend()
    config = TeammateSpawnConfig(
        name="reviewer",
        team="default",
        prompt="Review the code changes.",
        cwd=str(tmp_path),
        parent_session_id="sess-001",
        system_prompt="Project-specific addendum.",
        system_prompt_mode="append",
        task_type="local_agent",
    )

    result = await backend.spawn(config)

    assert result.success is True
    command = str(captured["command"])
    assert "--append-system-prompt" in command
    assert "Project-specific addendum." in command
