"""Tests for the /goal slash command."""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.commands.registry import CommandContext, create_default_command_registry
from openharness.config.settings import load_settings
from openharness.engine.query_engine import QueryEngine
from openharness.goal.store import GoalStore
from openharness.permissions import PermissionChecker
from openharness.tools import create_default_tool_registry


class FakeApiClient:
    async def stream_message(self, request):
        del request
        raise AssertionError("stream_message should not be called in command tests")


def _make_context(tmp_path: Path) -> CommandContext:
    return CommandContext(
        engine=QueryEngine(
            api_client=FakeApiClient(),
            tool_registry=create_default_tool_registry(),
            permission_checker=PermissionChecker(load_settings().permission),
            cwd=tmp_path,
            model="claude-test",
            system_prompt="system",
        ),
        cwd=str(tmp_path),
    )


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("OPENHARNESS_GOAL_VERIFIER_MODEL", raising=False)
    monkeypatch.delenv("OPENHARNESS_GOAL_MAX_TURNS", raising=False)
    monkeypatch.delenv("OPENHARNESS_GOAL_MAX_TOKENS", raising=False)
    return tmp_path


@pytest.mark.asyncio
async def test_goal_creates_goal_and_returns_it(isolated_env):
    registry = create_default_command_registry()
    command, args = registry.lookup("/goal fix the bug and run tests")
    assert command is not None
    result = await command.handler(args, _make_context(isolated_env))
    assert result.goal is not None
    assert result.goal.condition == "fix the bug and run tests"
    assert result.goal.status == "active"
    # Persisted immediately.
    assert GoalStore(isolated_env).load().condition == "fix the bug and run tests"


@pytest.mark.asyncio
async def test_goal_rejects_second_active_goal(isolated_env):
    registry = create_default_command_registry()
    context = _make_context(isolated_env)
    command, args = registry.lookup("/goal first goal")
    await command.handler(args, context)
    result = await command.handler("second goal", context)
    assert result.goal is None
    assert "already" in (result.message or "")


@pytest.mark.asyncio
async def test_goal_verifier_model_flag_wins(isolated_env):
    registry = create_default_command_registry()
    command, args = registry.lookup("/goal --verifier-model gpt-5-mini build it")
    result = await command.handler(args, _make_context(isolated_env))
    assert result.goal is not None
    assert result.goal.verifier_model == "gpt-5-mini"
    assert result.goal.condition == "build it"


@pytest.mark.asyncio
async def test_goal_verifier_model_from_env(isolated_env, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_GOAL_VERIFIER_MODEL", "gpt-5-nano")
    registry = create_default_command_registry()
    command, args = registry.lookup("/goal build it")
    result = await command.handler(args, _make_context(isolated_env))
    assert result.goal is not None
    assert result.goal.verifier_model == "gpt-5-nano"


@pytest.mark.asyncio
async def test_goal_max_turns_flag_and_env(isolated_env, monkeypatch):
    registry = create_default_command_registry()
    context = _make_context(isolated_env)

    command, args = registry.lookup("/goal --max-turns 7 do it")
    result = await command.handler(args, context)
    assert result.goal is not None
    assert result.goal.max_turns_budget == 7

    await command.handler("clear", context)
    monkeypatch.setenv("OPENHARNESS_GOAL_MAX_TURNS", "9")
    result = await command.handler("do it again", context)
    assert result.goal is not None
    assert result.goal.max_turns_budget == 9


@pytest.mark.asyncio
async def test_goal_status_show_and_clear(isolated_env):
    registry = create_default_command_registry()
    context = _make_context(isolated_env)

    status_command, status_args = registry.lookup("/goal status")
    status_result = await status_command.handler(status_args, context)
    assert "No goal set" in (status_result.message or "")

    create_command, _ = registry.lookup("/goal do the thing")
    await create_command.handler("do the thing", context)

    status_result = await status_command.handler(status_args, context)
    assert "do the thing" in (status_result.message or "")
    assert "Verifier model:" in (status_result.message or "")

    clear_command, clear_args = registry.lookup("/goal clear")
    clear_result = await clear_command.handler(clear_args, context)
    assert "cleared" in (clear_result.message or "")
    assert GoalStore(isolated_env).load() is None


@pytest.mark.asyncio
async def test_goal_pause_and_resume(isolated_env):
    registry = create_default_command_registry()
    context = _make_context(isolated_env)

    create_command, _ = registry.lookup("/goal make progress")
    await create_command.handler("make progress", context)
    pause_command, pause_args = registry.lookup("/goal pause")
    pause_result = await pause_command.handler(pause_args, context)
    assert "paused" in (pause_result.message or "")
    assert GoalStore(isolated_env).load().status == "paused"

    resume_command, resume_args = registry.lookup("/goal resume")
    resume_result = await resume_command.handler(resume_args, context)
    assert resume_result.goal is not None
    assert resume_result.goal.status == "active"


@pytest.mark.asyncio
async def test_goal_resume_completed_rejected(isolated_env):
    registry = create_default_command_registry()
    context = _make_context(isolated_env)

    create_command, _ = registry.lookup("/goal make progress")
    await create_command.handler("make progress", context)
    goal = GoalStore(isolated_env).load()
    goal.status = "completed"
    GoalStore(isolated_env).save(goal)

    resume_command, resume_args = registry.lookup("/goal resume")
    result = await resume_command.handler(resume_args, context)
    assert result.goal is None
    assert "completed" in (result.message or "")


@pytest.mark.asyncio
async def test_goal_hidden_from_remote_channels():
    registry = create_default_command_registry()
    command, _ = registry.lookup("/goal x")
    assert command is not None
    assert command.remote_invocable is False