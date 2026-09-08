"""Goal data model tests."""

from __future__ import annotations

from openharness.goal.types import GoalDefinition, VerifierVerdict


class TestGoalDefinition:
    def test_serialization_roundtrip(self):
        goal = GoalDefinition(
            condition="fix the bug and run tests",
            verifier_model="gpt-5-mini",
            max_turns_budget=10,
            max_tokens_budget=1000,
            turns_run=2,
            tokens_used=800,
            last_verdict=VerifierVerdict(
                done=False, confidence=0.7, rationale="still failing", next_step_hint="run pytest"
            ),
        )
        raw = goal.model_dump_json()
        restored = GoalDefinition.model_validate_json(raw)
        assert restored == goal

    def test_defaults(self):
        goal = GoalDefinition(condition="do X")
        assert goal.status == "active"
        assert goal.turns_run == 0
        assert goal.verifier_model == ""
        assert goal.max_turns_budget == 100
        assert goal.max_tokens_budget is None
        assert goal.last_verdict is None

    def test_budget_exhausted_by_turns(self):
        goal = GoalDefinition(condition="x", max_turns_budget=3, turns_run=3)
        assert goal.budget_exhausted(0) is True
        goal.turns_run = 2
        assert goal.budget_exhausted(0) is False

    def test_budget_exhausted_by_tokens(self):
        goal = GoalDefinition(condition="x", max_tokens_budget=500)
        assert goal.budget_exhausted(500) is True
        assert goal.budget_exhausted(499) is False

    def test_budget_unlimited_when_not_configured(self):
        goal = GoalDefinition(condition="x")
        assert goal.budget_exhausted(10**9) is False

    def test_touch_updates_timestamp(self):
        import time

        goal = GoalDefinition(condition="x")
        time.sleep(0.01)
        goal.touch()
        assert goal.updated_at >= goal.created_at