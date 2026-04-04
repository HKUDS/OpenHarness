"""Tests for TeamLifecycleManager CRUD operations with tmp_path fixtures."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from openharness.swarm.team_lifecycle import (
    TeamFile,
    TeamLifecycleManager,
    TeamMember,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manager(tmp_path, monkeypatch):
    """Return a TeamLifecycleManager whose teams live inside tmp_path."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return TeamLifecycleManager()


def _make_member(agent_id: str = "worker1@alpha", name: str = "worker1") -> TeamMember:
    return TeamMember(
        agent_id=agent_id,
        name=name,
        backend_type="subprocess",
        joined_at=time.time(),
    )


# ---------------------------------------------------------------------------
# TeamMember serialization
# ---------------------------------------------------------------------------


def test_team_member_round_trip():
    member = _make_member()
    data = member.to_dict()
    restored = TeamMember.from_dict(data)
    assert restored.agent_id == member.agent_id
    assert restored.name == member.name
    assert restored.backend_type == member.backend_type
    assert restored.status == "active"


def test_team_member_default_status():
    member = _make_member()
    assert member.status == "active"


# ---------------------------------------------------------------------------
# TeamFile serialization
# ---------------------------------------------------------------------------


def test_team_file_round_trip(tmp_path):
    tf = TeamFile(name="myteam", created_at=time.time(), description="test team")
    path = tmp_path / "team.json"
    tf.save(path)
    loaded = TeamFile.load(path)
    assert loaded.name == "myteam"
    assert loaded.description == "test team"


def test_team_file_load_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        TeamFile.load(tmp_path / "nonexistent.json")


# ---------------------------------------------------------------------------
# TeamLifecycleManager.create_team
# ---------------------------------------------------------------------------


def test_create_team_persists_to_disk(manager):
    tf = manager.create_team("alpha", "first team")
    assert tf.name == "alpha"
    assert tf.description == "first team"

    # Verify it was written to disk
    reloaded = manager.get_team("alpha")
    assert reloaded is not None
    assert reloaded.name == "alpha"


def test_create_team_duplicate_raises(manager):
    manager.create_team("beta")
    with pytest.raises(ValueError, match="already exists"):
        manager.create_team("beta")


# ---------------------------------------------------------------------------
# TeamLifecycleManager.get_team
# ---------------------------------------------------------------------------


def test_get_team_returns_none_for_missing(manager):
    result = manager.get_team("no-such-team")
    assert result is None


def test_get_team_returns_team_file(manager):
    manager.create_team("gamma")
    tf = manager.get_team("gamma")
    assert tf is not None
    assert tf.name == "gamma"


# ---------------------------------------------------------------------------
# TeamLifecycleManager.delete_team
# ---------------------------------------------------------------------------


def test_delete_team_removes_from_disk(manager):
    manager.create_team("to-delete")
    manager.delete_team("to-delete")
    assert manager.get_team("to-delete") is None


def test_delete_nonexistent_team_raises(manager):
    with pytest.raises(ValueError, match="does not exist"):
        manager.delete_team("ghost")


# ---------------------------------------------------------------------------
# TeamLifecycleManager.list_teams
# ---------------------------------------------------------------------------


def test_list_teams_empty_initially(manager):
    teams = manager.list_teams()
    assert teams == []


def test_list_teams_returns_all_sorted(manager):
    for name in ("charlie", "alpha", "bravo"):
        manager.create_team(name)
    teams = manager.list_teams()
    names = [t.name for t in teams]
    assert names == sorted(names)
    assert set(names) == {"alpha", "bravo", "charlie"}


# ---------------------------------------------------------------------------
# TeamLifecycleManager.add_member / remove_member
# ---------------------------------------------------------------------------


def test_add_member_persists(manager):
    manager.create_team("delta")
    member = _make_member()
    updated = manager.add_member("delta", member)
    assert member.agent_id in updated.members

    reloaded = manager.get_team("delta")
    assert reloaded is not None
    assert member.agent_id in reloaded.members


def test_add_member_replaces_existing(manager):
    manager.create_team("epsilon")
    m1 = TeamMember(
        agent_id="w@epsilon", name="old", backend_type="subprocess", joined_at=1.0
    )
    manager.add_member("epsilon", m1)

    m2 = TeamMember(
        agent_id="w@epsilon", name="new", backend_type="in_process", joined_at=2.0
    )
    updated = manager.add_member("epsilon", m2)
    assert updated.members["w@epsilon"].name == "new"


def test_remove_member(manager):
    manager.create_team("zeta")
    member = _make_member("x@zeta", "x")
    manager.add_member("zeta", member)
    updated = manager.remove_member("zeta", "x@zeta")
    assert "x@zeta" not in updated.members


def test_remove_nonexistent_member_raises(manager):
    manager.create_team("eta")
    with pytest.raises(ValueError, match="not a member"):
        manager.remove_member("eta", "ghost@eta")


def test_add_member_to_nonexistent_team_raises(manager):
    with pytest.raises(ValueError, match="does not exist"):
        manager.add_member("no-team", _make_member())
