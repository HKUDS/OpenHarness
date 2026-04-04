"""Tests for CoordinatorMode, TaskNotification XML, and WorkerConfig."""

from __future__ import annotations

import pytest

from openharness.coordinator.coordinator_mode import (
    TaskNotification,
    WorkerConfig,
    format_task_notification,
    get_coordinator_tools,
    get_coordinator_user_context,
    is_coordinator_mode,
    match_session_mode,
    parse_task_notification,
)


# ---------------------------------------------------------------------------
# TaskNotification XML round-trip
# ---------------------------------------------------------------------------


def test_format_and_parse_basic():
    n = TaskNotification(task_id="t123", status="completed", summary="all done")
    xml = format_task_notification(n)
    assert "<task-notification>" in xml
    assert "<task-id>t123</task-id>" in xml
    assert "<status>completed</status>" in xml
    assert "<summary>all done</summary>" in xml

    parsed = parse_task_notification(xml)
    assert parsed.task_id == "t123"
    assert parsed.status == "completed"
    assert parsed.summary == "all done"
    assert parsed.result is None
    assert parsed.usage is None


def test_format_and_parse_with_result_and_usage():
    n = TaskNotification(
        task_id="abc",
        status="failed",
        summary="error occurred",
        result="traceback here",
        usage={"total_tokens": 42, "tool_uses": 3, "duration_ms": 1500},
    )
    xml = format_task_notification(n)
    assert "<result>traceback here</result>" in xml
    assert "<total_tokens>42</total_tokens>" in xml
    assert "<tool_uses>3</tool_uses>" in xml
    assert "<duration_ms>1500</duration_ms>" in xml

    parsed = parse_task_notification(xml)
    assert parsed.task_id == "abc"
    assert parsed.status == "failed"
    assert parsed.result == "traceback here"
    assert parsed.usage == {"total_tokens": 42, "tool_uses": 3, "duration_ms": 1500}


def test_parse_ignores_missing_optional_fields():
    xml = "<task-notification><task-id>x</task-id><status>completed</status><summary>ok</summary></task-notification>"
    parsed = parse_task_notification(xml)
    assert parsed.task_id == "x"
    assert parsed.result is None
    assert parsed.usage is None


def test_parse_partial_usage_block():
    xml = (
        "<task-notification>"
        "<task-id>y</task-id><status>completed</status><summary>ok</summary>"
        "<usage><total_tokens>100</total_tokens></usage>"
        "</task-notification>"
    )
    parsed = parse_task_notification(xml)
    assert parsed.usage == {"total_tokens": 100}


# ---------------------------------------------------------------------------
# is_coordinator_mode
# ---------------------------------------------------------------------------


def test_is_coordinator_mode_false_by_default(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    assert is_coordinator_mode() is False


@pytest.mark.parametrize("value", ["1", "true", "True", "yes", "YES"])
def test_is_coordinator_mode_true_variants(monkeypatch, value):
    monkeypatch.setenv("CLAUDE_CODE_COORDINATOR_MODE", value)
    assert is_coordinator_mode() is True


def test_is_coordinator_mode_false_for_garbage(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_COORDINATOR_MODE", "maybe")
    assert is_coordinator_mode() is False


# ---------------------------------------------------------------------------
# get_coordinator_tools
# ---------------------------------------------------------------------------


def test_get_coordinator_tools_returns_expected():
    tools = get_coordinator_tools()
    assert "agent" in tools
    assert "send_message" in tools
    assert "task_stop" in tools
    assert len(tools) == 3


# ---------------------------------------------------------------------------
# match_session_mode
# ---------------------------------------------------------------------------


def test_match_session_mode_no_change_when_already_coordinator(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_COORDINATOR_MODE", "1")
    result = match_session_mode("coordinator")
    assert result is None
    assert is_coordinator_mode() is True


def test_match_session_mode_switches_to_coordinator(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    result = match_session_mode("coordinator")
    assert result is not None
    assert "coordinator" in result.lower()
    assert is_coordinator_mode() is True


def test_match_session_mode_exits_coordinator(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_COORDINATOR_MODE", "1")
    result = match_session_mode("worker")
    assert result is not None
    assert is_coordinator_mode() is False


def test_match_session_mode_none_returns_none(monkeypatch):
    result = match_session_mode(None)
    assert result is None


# ---------------------------------------------------------------------------
# get_coordinator_user_context
# ---------------------------------------------------------------------------


def test_coordinator_user_context_empty_when_not_coordinator(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    ctx = get_coordinator_user_context()
    assert ctx == {}


def test_coordinator_user_context_includes_tools(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_COORDINATOR_MODE", "1")
    monkeypatch.delenv("CLAUDE_CODE_SIMPLE", raising=False)
    ctx = get_coordinator_user_context()
    assert "workerToolsContext" in ctx
    assert "bash" in ctx["workerToolsContext"]


def test_coordinator_user_context_with_mcp_clients(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_COORDINATOR_MODE", "1")
    ctx = get_coordinator_user_context(mcp_clients=[{"name": "my-server"}])
    assert "my-server" in ctx["workerToolsContext"]


def test_coordinator_user_context_with_scratchpad(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_COORDINATOR_MODE", "1")
    ctx = get_coordinator_user_context(scratchpad_dir="/tmp/scratch")
    assert "/tmp/scratch" in ctx["workerToolsContext"]


# ---------------------------------------------------------------------------
# WorkerConfig dataclass
# ---------------------------------------------------------------------------


def test_worker_config_defaults():
    cfg = WorkerConfig(agent_id="w1", name="coder", prompt="do stuff")
    assert cfg.model is None
    assert cfg.color is None
    assert cfg.team is None


def test_worker_config_full():
    cfg = WorkerConfig(
        agent_id="w2",
        name="tester",
        prompt="run tests",
        model="claude-opus-4-6",
        color="blue",
        team="alpha",
    )
    assert cfg.model == "claude-opus-4-6"
    assert cfg.team == "alpha"
