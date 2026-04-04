"""Tests for swarm type definitions: TeammateIdentity, SpawnResult, TeammateExecutor."""

from __future__ import annotations


from openharness.swarm.types import (
    SpawnResult,
    TeammateExecutor,
    TeammateIdentity,
    TeammateMessage,
    TeammateSpawnConfig,
)


# ---------------------------------------------------------------------------
# TeammateIdentity
# ---------------------------------------------------------------------------


def test_teammate_identity_required_fields():
    identity = TeammateIdentity(agent_id="coder@alpha", name="coder", team="alpha")
    assert identity.agent_id == "coder@alpha"
    assert identity.name == "coder"
    assert identity.team == "alpha"
    assert identity.color is None
    assert identity.parent_session_id is None


def test_teammate_identity_with_optional_fields():
    identity = TeammateIdentity(
        agent_id="r@t",
        name="r",
        team="t",
        color="blue",
        parent_session_id="sess-123",
    )
    assert identity.color == "blue"
    assert identity.parent_session_id == "sess-123"


# ---------------------------------------------------------------------------
# SpawnResult
# ---------------------------------------------------------------------------


def test_spawn_result_success_defaults():
    result = SpawnResult(task_id="t1", agent_id="a@b", backend_type="subprocess")
    assert result.success is True
    assert result.error is None


def test_spawn_result_failure():
    result = SpawnResult(
        task_id="",
        agent_id="a@b",
        backend_type="in_process",
        success=False,
        error="already running",
    )
    assert result.success is False
    assert result.error == "already running"


def test_spawn_result_backend_types():
    for bt in ("subprocess", "in_process", "tmux"):
        r = SpawnResult(task_id="x", agent_id="a@b", backend_type=bt)
        assert r.backend_type == bt


# ---------------------------------------------------------------------------
# TeammateMessage
# ---------------------------------------------------------------------------


def test_teammate_message_required():
    msg = TeammateMessage(text="hello", from_agent="leader")
    assert msg.text == "hello"
    assert msg.from_agent == "leader"
    assert msg.color is None
    assert msg.timestamp is None
    assert msg.summary is None


def test_teammate_message_full():
    msg = TeammateMessage(
        text="do this",
        from_agent="boss",
        color="green",
        timestamp="2026-01-01T00:00:00",
        summary="a task",
    )
    assert msg.color == "green"
    assert msg.summary == "a task"


# ---------------------------------------------------------------------------
# TeammateSpawnConfig
# ---------------------------------------------------------------------------


def test_teammate_spawn_config_defaults():
    cfg = TeammateSpawnConfig(
        name="worker",
        team="myteam",
        prompt="do work",
        cwd="/tmp",
        parent_session_id="sess",
    )
    assert cfg.model is None
    assert cfg.system_prompt is None
    assert cfg.color is None
    assert cfg.permissions == []
    assert cfg.plan_mode_required is False
    assert cfg.allow_permission_prompts is False


# ---------------------------------------------------------------------------
# TeammateExecutor protocol structural check
# ---------------------------------------------------------------------------


def test_teammate_executor_is_protocol():
    """TeammateExecutor is a runtime_checkable Protocol."""

    class MockExecutor:
        type = "subprocess"

        def is_available(self) -> bool:
            return True

        async def spawn(self, config):
            ...

        async def send_message(self, agent_id, message):
            ...

        async def shutdown(self, agent_id, *, force=False):
            ...

    executor = MockExecutor()
    assert isinstance(executor, TeammateExecutor)


def test_teammate_executor_missing_method_fails_check():
    class IncompleteExecutor:
        type = "subprocess"

        def is_available(self) -> bool:
            return True

        # Missing: spawn, send_message, shutdown

    incomplete = IncompleteExecutor()
    assert not isinstance(incomplete, TeammateExecutor)
