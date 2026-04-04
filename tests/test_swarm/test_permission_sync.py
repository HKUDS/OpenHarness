"""Tests for swarm permission sync protocol: create/send/poll/handle."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from openharness.swarm.permission_sync import (
    SwarmPermissionResponse,
    _is_read_only,
    create_permission_request,
    handle_permission_request,
    poll_permission_response,
    send_permission_request,
    send_permission_response,
)


# ---------------------------------------------------------------------------
# _is_read_only heuristic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name",
    ["Read", "Glob", "Grep", "WebFetch", "WebSearch", "TaskGet", "TaskList", "CronList"],
)
def test_is_read_only_true_for_safe_tools(tool_name):
    assert _is_read_only(tool_name) is True


@pytest.mark.parametrize("tool_name", ["Bash", "Edit", "Write", "TaskCreate"])
def test_is_read_only_false_for_write_tools(tool_name):
    assert _is_read_only(tool_name) is False


# ---------------------------------------------------------------------------
# create_permission_request
# ---------------------------------------------------------------------------


def test_create_permission_request_has_unique_id():
    r1 = create_permission_request("Bash", "tu-1", {"command": "ls"})
    r2 = create_permission_request("Bash", "tu-2", {"command": "ls"})
    assert r1.id != r2.id


def test_create_permission_request_fields():
    req = create_permission_request(
        "Edit",
        "tu-xyz",
        {"file_path": "/tmp/f.py"},
        description="edit a file",
        permission_suggestions=[{"type": "allow"}],
    )
    assert req.tool_name == "Edit"
    assert req.tool_use_id == "tu-xyz"
    assert req.description == "edit a file"
    assert req.permission_suggestions == [{"type": "allow"}]


def test_create_permission_request_default_suggestions():
    req = create_permission_request("Bash", "tu-1", {})
    assert req.permission_suggestions == []


# ---------------------------------------------------------------------------
# SwarmPermissionResponse
# ---------------------------------------------------------------------------


def test_swarm_permission_response_defaults():
    resp = SwarmPermissionResponse(request_id="r1", allowed=True)
    assert resp.feedback is None
    assert resp.updated_rules == []


# ---------------------------------------------------------------------------
# send_permission_request writes to leader mailbox
# ---------------------------------------------------------------------------


async def test_send_permission_request_writes_to_leader(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    req = create_permission_request("Bash", "tu-1", {"command": "echo hi"})
    await send_permission_request(req, "myteam", "worker1", "leader")

    from openharness.swarm.mailbox import TeammateMailbox
    mailbox = TeammateMailbox("myteam", "leader")
    messages = await mailbox.read_all(unread_only=False)
    assert len(messages) == 1
    assert messages[0].type == "permission_request"
    assert messages[0].payload["tool_name"] == "Bash"
    assert messages[0].payload["worker_id"] == "worker1"


# ---------------------------------------------------------------------------
# send_permission_response writes to worker mailbox
# ---------------------------------------------------------------------------


async def test_send_permission_response_writes_to_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    resp = SwarmPermissionResponse(request_id="r1", allowed=True, feedback=None)
    await send_permission_response(resp, "myteam", "worker1", "leader")

    from openharness.swarm.mailbox import TeammateMailbox
    mailbox = TeammateMailbox("myteam", "worker1")
    messages = await mailbox.read_all(unread_only=False)
    assert len(messages) == 1
    assert messages[0].type == "permission_response"
    assert messages[0].payload["allowed"] is True


# ---------------------------------------------------------------------------
# handle_permission_request
# ---------------------------------------------------------------------------


async def test_handle_read_only_tool_auto_approved():
    req = create_permission_request("Read", "tu-1", {"file_path": "/tmp/f.py"})
    checker = MagicMock()
    resp = await handle_permission_request(req, checker)
    assert resp.allowed is True
    checker.evaluate.assert_not_called()


async def test_handle_write_tool_delegates_to_checker():
    req = create_permission_request("Bash", "tu-2", {"command": "rm -rf /"})

    decision = MagicMock()
    decision.allowed = False
    decision.reason = "dangerous command"
    checker = MagicMock()
    checker.evaluate.return_value = decision

    resp = await handle_permission_request(req, checker)
    assert resp.allowed is False
    assert resp.feedback == "dangerous command"
    checker.evaluate.assert_called_once_with(
        "Bash", is_read_only=False, file_path=None, command="rm -rf /"
    )


async def test_handle_write_tool_allowed_by_checker():
    req = create_permission_request("Edit", "tu-3", {"file_path": "/src/main.py"})

    decision = MagicMock()
    decision.allowed = True
    decision.reason = None
    checker = MagicMock()
    checker.evaluate.return_value = decision

    resp = await handle_permission_request(req, checker)
    assert resp.allowed is True
    assert resp.feedback is None


# ---------------------------------------------------------------------------
# poll_permission_response timeout
# ---------------------------------------------------------------------------


async def test_poll_permission_response_times_out(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = await poll_permission_response("myteam", "worker1", "nonexistent-id", timeout=0.1)
    assert result is None


async def test_poll_permission_response_finds_matching_message(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Pre-write a response to the worker mailbox
    resp = SwarmPermissionResponse(request_id="req-abc", allowed=True)
    await send_permission_response(resp, "myteam", "worker1", "leader")

    result = await poll_permission_response("myteam", "worker1", "req-abc", timeout=2.0)
    assert result is not None
    assert result.allowed is True
    assert result.request_id == "req-abc"
