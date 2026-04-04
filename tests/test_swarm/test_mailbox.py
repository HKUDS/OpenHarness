"""Tests for TeammateMailbox: write/read/mark_read/clear and factory helpers."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from openharness.swarm.mailbox import (
    MailboxMessage,
    TeammateMailbox,
    create_idle_notification,
    create_shutdown_request,
    create_user_message,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mailbox(tmp_path, monkeypatch):
    """Return a TeammateMailbox whose team directory is inside tmp_path."""
    # Redirect the home-dir lookup so mailbox writes to tmp_path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return TeammateMailbox(team_name="test-team", agent_id="worker1")


def _make_msg(sender="leader", recipient="worker1") -> MailboxMessage:
    return MailboxMessage(
        id="msg-001",
        type="user_message",
        sender=sender,
        recipient=recipient,
        payload={"content": "hello"},
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# MailboxMessage serialisation
# ---------------------------------------------------------------------------


def test_mailbox_message_round_trip():
    msg = _make_msg()
    d = msg.to_dict()
    msg2 = MailboxMessage.from_dict(d)
    assert msg2.id == msg.id
    assert msg2.type == msg.type
    assert msg2.sender == msg.sender
    assert msg2.payload == msg.payload
    assert msg2.read is False


def test_mailbox_message_from_dict_defaults_read_false():
    data = {
        "id": "x",
        "type": "user_message",
        "sender": "a",
        "recipient": "b",
        "payload": {},
        "timestamp": 1234.0,
    }
    msg = MailboxMessage.from_dict(data)
    assert msg.read is False


# ---------------------------------------------------------------------------
# TeammateMailbox write / read_all
# ---------------------------------------------------------------------------


async def test_write_and_read_all(mailbox):
    msg = _make_msg()
    await mailbox.write(msg)
    messages = await mailbox.read_all(unread_only=False)
    assert len(messages) == 1
    assert messages[0].id == "msg-001"


async def test_read_all_unread_only_filters(mailbox):
    msg = _make_msg()
    await mailbox.write(msg)

    # Mark it read directly by re-writing with read=True
    inbox = mailbox.get_mailbox_dir()
    for path in inbox.glob("*.json"):
        import json as _json
        data = _json.loads(path.read_text())
        data["read"] = True
        path.write_text(_json.dumps(data))

    unread = await mailbox.read_all(unread_only=True)
    assert unread == []

    all_msgs = await mailbox.read_all(unread_only=False)
    assert len(all_msgs) == 1


async def test_write_multiple_messages_sorted_by_timestamp(mailbox):
    for i in range(3):
        msg = MailboxMessage(
            id=f"msg-{i}",
            type="user_message",
            sender="leader",
            recipient="worker1",
            payload={"seq": i},
            timestamp=1000.0 + i,
        )
        await mailbox.write(msg)

    messages = await mailbox.read_all(unread_only=False)
    timestamps = [m.timestamp for m in messages]
    assert timestamps == sorted(timestamps)


# ---------------------------------------------------------------------------
# mark_read
# ---------------------------------------------------------------------------


async def test_mark_read_updates_flag(mailbox):
    msg = _make_msg()
    await mailbox.write(msg)

    await mailbox.mark_read(msg.id)
    all_msgs = await mailbox.read_all(unread_only=False)
    assert all_msgs[0].read is True


async def test_mark_read_nonexistent_id_is_noop(mailbox):
    msg = _make_msg()
    await mailbox.write(msg)
    # Should not raise
    await mailbox.mark_read("does-not-exist")
    # Original message still unread
    messages = await mailbox.read_all(unread_only=True)
    assert len(messages) == 1


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


async def test_clear_removes_all_messages(mailbox):
    for i in range(3):
        msg = MailboxMessage(
            id=f"c-{i}",
            type="user_message",
            sender="l",
            recipient="w",
            payload={},
            timestamp=float(i),
        )
        await mailbox.write(msg)

    await mailbox.clear()
    messages = await mailbox.read_all(unread_only=False)
    assert messages == []


async def test_clear_on_empty_mailbox_is_noop(mailbox):
    await mailbox.clear()  # should not raise
    messages = await mailbox.read_all(unread_only=False)
    assert messages == []


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def test_create_user_message():
    msg = create_user_message("leader", "worker1", "do stuff")
    assert msg.type == "user_message"
    assert msg.sender == "leader"
    assert msg.recipient == "worker1"
    assert msg.payload["content"] == "do stuff"
    assert msg.id  # has a UUID


def test_create_shutdown_request():
    msg = create_shutdown_request("leader", "worker1")
    assert msg.type == "shutdown"
    assert msg.payload == {}


def test_create_idle_notification():
    msg = create_idle_notification("worker1", "leader", "finished task")
    assert msg.type == "idle_notification"
    assert msg.payload["summary"] == "finished task"
