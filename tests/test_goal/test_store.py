"""GoalStore persistence tests."""

from __future__ import annotations

from openharness.goal.store import GoalStore
from openharness.goal.types import GoalDefinition


class TestGoalStore:
    def test_save_load_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
        store = GoalStore(tmp_path / "proj")
        goal = GoalDefinition(condition="do the thing", max_turns_budget=7)
        store.save(goal)

        loaded = store.load()
        assert loaded is not None
        assert loaded.condition == "do the thing"
        assert loaded.max_turns_budget == 7
        assert loaded.goal_id == goal.goal_id

    def test_load_missing_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
        store = GoalStore(tmp_path / "proj")
        assert store.load() is None

    def test_clear_removes_state(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
        store = GoalStore(tmp_path / "proj")
        store.save(GoalDefinition(condition="x"))
        assert store.load() is not None
        store.clear()
        assert store.load() is None

    def test_save_roundtrip_survives_new_store_instance(self, tmp_path, monkeypatch):
        """A new GoalStore instance (stand-in for a restarted process) reads
        the same persisted state."""
        monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
        first = GoalStore(tmp_path / "proj")
        first.save(GoalDefinition(condition="x", turns_run=4))

        second = GoalStore(tmp_path / "proj")
        loaded = second.load()
        assert loaded is not None
        assert loaded.turns_run == 4

    def test_load_corrupt_file_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
        store = GoalStore(tmp_path / "proj")
        store.file_path.parent.mkdir(parents=True, exist_ok=True)
        store.file_path.write_text("{not json", encoding="utf-8")
        assert store.load() is None

    def test_projects_are_isolated(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
        store_a = GoalStore(tmp_path / "proj-a")
        store_b = GoalStore(tmp_path / "proj-b")
        store_a.save(GoalDefinition(condition="goal a"))
        assert store_b.load() is None