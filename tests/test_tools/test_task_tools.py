"""Tests for task and team tools."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from openharness.coordinator.coordinator_mode import get_team_registry
from openharness.tasks import get_task_manager
from openharness.tools.agent_tool import AgentTool, AgentToolInput
from openharness.tools.base import ToolExecutionContext
from openharness.tools.task_create_tool import TaskCreateTool, TaskCreateToolInput
from openharness.tools.task_output_tool import TaskOutputTool, TaskOutputToolInput
from openharness.tools.task_update_tool import TaskUpdateTool, TaskUpdateToolInput
from openharness.tools.team_create_tool import TeamCreateTool, TeamCreateToolInput


@pytest.mark.asyncio
async def test_task_create_and_output_tool(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    context = ToolExecutionContext(cwd=tmp_path)

    create_result = await TaskCreateTool().execute(
        TaskCreateToolInput(
            type="local_bash",
            description="echo",
            command="printf 'tool task'",
        ),
        context,
    )
    assert create_result.is_error is False
    task_id = create_result.output.split()[2]

    manager = get_task_manager()
    for _ in range(20):
        if "tool task" in manager.read_task_output(task_id):
            break
        await asyncio.sleep(0.1)
    output_result = await TaskOutputTool().execute(
        TaskOutputToolInput(task_id=task_id),
        context,
    )
    assert "tool task" in output_result.output


@pytest.mark.asyncio
async def test_team_create_tool(tmp_path: Path):
    result = await TeamCreateTool().execute(
        TeamCreateToolInput(name="demo", description="test"),
        ToolExecutionContext(cwd=tmp_path),
    )
    assert result.is_error is False
    assert "Created team demo" == result.output


@pytest.mark.asyncio
async def test_task_update_tool_updates_metadata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    context = ToolExecutionContext(cwd=tmp_path)

    create_result = await TaskCreateTool().execute(
        TaskCreateToolInput(
            type="local_bash",
            description="updatable",
            command="printf 'tool task'",
        ),
        context,
    )
    task_id = create_result.output.split()[2]

    update_result = await TaskUpdateTool().execute(
        TaskUpdateToolInput(
            task_id=task_id,
            progress=60,
            status_note="waiting on verification",
            description="renamed task",
        ),
        context,
    )
    assert update_result.is_error is False

    task = get_task_manager().get_task(task_id)
    assert task is not None
    assert task.description == "renamed task"
    assert task.metadata["progress"] == "60"
    assert task.metadata["status_note"] == "waiting on verification"


@pytest.mark.asyncio
async def test_agent_tool_uses_subprocess_backend_and_task_is_pollable(
    tmp_path: Path, monkeypatch
):
    """Regression test for #59 / PR #60.

    AgentTool must use the subprocess backend so the returned task_id is
    registered in BackgroundTaskManager and is queryable by the task tools.

    Before the fix, AgentTool hardcoded in_process first.  On macOS/Linux that
    backend is always registered (supports_swarm_mailbox=True), so spawn()
    returned IDs like "in_process_3f7a9b1c2d4e" that BackgroundTaskManager
    never saw — every poll attempt raised ValueError.
    """
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    context = ToolExecutionContext(cwd=tmp_path)

    result = await AgentTool().execute(
        AgentToolInput(
            description="backend regression check",
            prompt="hello",
            subagent_type="test-worker",
            # command echoes one line and exits — minimal subprocess
            command='python -u -c "import sys; print(sys.stdin.readline().strip())"',
        ),
        context,
    )

    assert not result.is_error, f"AgentTool failed: {result.output}"

    # 1. Backend reported in output must be subprocess, not in_process.
    assert "backend=subprocess" in result.output, (
        f"Expected backend=subprocess in output, got: {result.output}"
    )

    # 2. task_id must NOT be an in-process ID.
    assert "in_process_" not in result.output, (
        f"task_id must not be an in-process ID, got: {result.output}"
    )

    # 3. The task_id must be registered in BackgroundTaskManager so task tools
    #    can query it without raising ValueError.
    #    Parse task_id from "Spawned agent X (task_id=Y, backend=Z)"
    import re
    m = re.search(r"task_id=(\S+?)[,)]", result.output)
    assert m, f"Could not parse task_id from output: {result.output}"
    task_id = m.group(1)

    manager = get_task_manager()
    record = manager.get_task(task_id)
    assert record is not None, (
        f"task_id {task_id!r} not found in BackgroundTaskManager — "
        "task tools (TaskGet, TaskOutput, etc.) would have failed"
    )
    assert record.command is not None
    assert "--task-worker" in record.command


@pytest.mark.asyncio
async def test_send_message_swarm_path_uses_subprocess_backend(
    tmp_path: Path, monkeypatch
):
    """SendMessageTool._send_swarm_message must route via SubprocessBackend.

    Before the fix, _send_swarm_message also hardcoded in_process, so even
    the name@team routing path would fail to find agents spawned by AgentTool.
    """
    from unittest.mock import AsyncMock, patch

    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    context = ToolExecutionContext(cwd=tmp_path)

    from openharness.tools.send_message_tool import SendMessageTool

    with patch(
        "openharness.swarm.subprocess_backend.SubprocessBackend.send_message",
        new_callable=AsyncMock,
    ) as mock_send:
        await SendMessageTool().execute(
            __import__(
                "openharness.tools.send_message_tool",
                fromlist=["SendMessageToolInput"],
            ).SendMessageToolInput(
                task_id="worker@default",
                message="ping",
            ),
            context,
        )

    # send_message may raise ValueError because no agent was spawned yet
    # (no _agent_tasks entry), but the key assertion is that SubprocessBackend
    # was called — not InProcessBackend.
    mock_send.assert_called_once()
    agent_id_arg = mock_send.call_args[0][0]
    assert agent_id_arg == "worker@default"


@pytest.mark.asyncio
async def test_agent_tool_creates_missing_team_when_team_argument_is_provided(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    get_team_registry()._teams.clear()
    context = ToolExecutionContext(cwd=tmp_path)

    result = await AgentTool().execute(
        AgentToolInput(
            description="team auto-create regression",
            prompt="ready",
            subagent_type="test-worker-team",
            team="design-qa-loop",
            command="python -u -c \"import sys; print(sys.stdin.readline().strip())\"",
        ),
        context,
    )

    assert result.is_error is False
    teams = {team.name: team for team in get_team_registry().list_teams()}
    assert "design-qa-loop" in teams
    assert len(teams["design-qa-loop"].agents) == 1


@pytest.mark.asyncio
async def test_agent_tool_supports_remote_and_teammate_modes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    context = ToolExecutionContext(cwd=tmp_path)

    for i, mode in enumerate(("remote_agent", "in_process_teammate")):
        result = await AgentTool().execute(
            AgentToolInput(
                description=f"{mode} smoke",
                prompt="ready",
                mode=mode,
                subagent_type=f"test-worker-{i}",
                command="python -u -c \"import sys; print(sys.stdin.readline().strip())\"",
            ),
            context,
        )
        assert result.is_error is False
        # Output format: "Spawned agent X (task_id=Y, backend=Z)"
        assert "agent" in result.output.lower() or "task_id" in result.output.lower()
