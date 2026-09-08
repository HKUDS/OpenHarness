"""Tests for the goal runner loop with fakes for the engine and verifier."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from openharness.api.client import ApiTextDeltaEvent
from openharness.api.usage import UsageSnapshot
from openharness.config.settings import Settings
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.engine.stream_events import AssistantTurnComplete, StreamEvent
from openharness.goal.prompts import build_goal_system_block
from openharness.goal.runner import run_goal_loop
from openharness.goal.store import GoalStore
from openharness.goal.types import GoalDefinition


class FakeVerifierClient:
    """Yields a canned verdict per call from ``verdicts`` (dicts or errors)."""

    def __init__(self, verdicts):
        self.verdicts = list(verdicts)
        self.calls = []

    async def stream_message(self, request):
        self.calls.append(request)
        item = self.verdicts.pop(0) if self.verdicts else {"done": True}
        if isinstance(item, Exception):
            raise item
        yield ApiTextDeltaEvent(text=json.dumps(item))


class SlowVerifierClient(FakeVerifierClient):
    """Yields a done verdict after sleeping, simulating a hung upstream."""

    def __init__(self, sleep_seconds):
        super().__init__([])
        self.sleep_seconds = sleep_seconds

    async def stream_message(self, request):
        self.calls.append(request)
        await asyncio.sleep(self.sleep_seconds)
        yield ApiTextDeltaEvent(text=json.dumps({"done": True}))


class FakeEngine:
    def __init__(self, verifier_client, tokens_per_turn=0):
        self.api_client = verifier_client
        self.model = "test-model"
        self._messages = [ConversationMessage.from_user_text("initial")]
        self._usage = UsageSnapshot()
        self._tokens_per_turn = tokens_per_turn
        self._system_prompt = "base system prompt"
        self.submitted_prompts = []
        self.max_turns_set = []
        self._fail_next_submit = False

    @property
    def messages(self):
        return self._messages

    @property
    def total_usage(self):
        return self._usage

    @property
    def system_prompt(self):
        return self._system_prompt

    def set_system_prompt(self, prompt):
        self._system_prompt = prompt

    def set_max_turns(self, turns):
        self.max_turns_set.append(turns)

    def load_messages(self, messages):
        self._messages = list(messages)

    @property
    def tool_metadata(self):
        return {}

    async def submit_message(self, prompt):
        if self._fail_next_submit:
            self._fail_next_submit = False
            from openharness.engine.query import MaxTurnsExceeded

            raise MaxTurnsExceeded(1)
        self.submitted_prompts.append(prompt)
        self._messages.append(ConversationMessage.from_user_text(prompt))
        self._messages.append(
            ConversationMessage(role="assistant", content=[TextBlock(text="working...")])
        )
        self._usage = UsageSnapshot(
            input_tokens=self._usage.input_tokens + self._tokens_per_turn,
            output_tokens=self._usage.output_tokens + 10,
        )
        yield AssistantTurnComplete(
            message=self._messages[-1], usage=self._usage
        )


class FakeSessionBackend:
    def __init__(self):
        self.snapshots = []
        self._latest_snapshot = None

    async def save_snapshot(self, **kwargs):
        del kwargs
        self.snapshots.append(1)

    def load_latest(self, cwd):
        return self._latest_snapshot


class FakeBundle:
    def __init__(self, engine, cwd, enforce_max_turns=True):
        self.engine = engine
        self.cwd = str(cwd)
        self.enforce_max_turns = enforce_max_turns
        self.session_id = "sess-1"
        self.session_backend = FakeSessionBackend()

    def current_settings(self):
        return Settings()


async def _collect_events(events):
    return [event async for event in events]


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


async def _noop_render(event: StreamEvent) -> None:
    del event


async def _run(bundle, goal, prints=None, verifier_timeout=None):
    printed = []

    async def print_system(message: str) -> None:
        printed.append(message)

    kwargs = {} if verifier_timeout is None else {"verifier_timeout": verifier_timeout}
    await run_goal_loop(bundle, goal, _noop_render, print_system, **kwargs)
    return printed


@pytest.mark.asyncio
async def test_loop_completes_when_verifier_says_done(isolated_env):
    engine = FakeEngine(FakeVerifierClient([{"done": True, "rationale": "tests pass"}]))
    bundle = FakeBundle(engine, isolated_env)
    goal = GoalDefinition(condition="fix the bug", max_turns_budget=10)

    printed = await _run(bundle, goal)

    assert goal.status == "completed"
    assert goal.turns_run == 1
    assert len(engine.submitted_prompts) == 1  # first turn only
    assert engine.submitted_prompts[0] == "fix the bug"
    assert any("Completed" in line for line in printed)
    # Goal context injected into the main system prompt.
    assert build_goal_system_block("fix the bug") in engine.system_prompt


@pytest.mark.asyncio
async def test_loop_continues_until_verifier_says_done(isolated_env):
    verdicts = [
        {"done": False, "rationale": "still red", "next_step_hint": "run tests"},
        {"done": False, "rationale": "one more", "next_step_hint": "fix assertion"},
        {"done": True},
    ]
    engine = FakeEngine(FakeVerifierClient(verdicts))
    bundle = FakeBundle(engine, isolated_env)
    goal = GoalDefinition(condition="ship it", max_turns_budget=10)

    await _run(bundle, goal)

    assert goal.status == "completed"
    assert goal.turns_run == 3
    assert engine.submitted_prompts == ["ship it", "run tests", "fix assertion"]
    assert goal.last_verdict is not None and goal.last_verdict.done


@pytest.mark.asyncio
async def test_loop_stops_on_turn_budget(isolated_env):
    # Verifier never says done; budget forces failure after the allotted turns.
    engine = FakeEngine(FakeVerifierClient([{"done": False, "next_step_hint": "keep going"}] * 10))
    bundle = FakeBundle(engine, isolated_env)
    goal = GoalDefinition(condition="endless", max_turns_budget=3)

    printed = await _run(bundle, goal)

    assert goal.status == "failed"
    assert goal.turns_run == 3
    assert any("Budget exhausted" in line for line in printed)


@pytest.mark.asyncio
async def test_loop_stops_on_token_budget(isolated_env):
    engine = FakeEngine(
        FakeVerifierClient([{"done": False, "next_step_hint": "keep going"}] * 5),
        tokens_per_turn=100,
    )
    bundle = FakeBundle(engine, isolated_env)
    goal = GoalDefinition(condition="thirsty", max_tokens_budget=250)

    await _run(bundle, goal)

    assert goal.status == "failed"
    assert engine.total_usage.total_tokens >= 250


@pytest.mark.asyncio
async def test_loop_resumes_without_first_turn(isolated_env):
    engine = FakeEngine(FakeVerifierClient([{"done": True}]))
    bundle = FakeBundle(engine, isolated_env)
    goal = GoalDefinition(condition="resumed goal", max_turns_budget=10, turns_run=2)

    await _run(bundle, goal)

    assert goal.status == "completed"
    assert engine.submitted_prompts == []  # no first turn on resume


@pytest.mark.asyncio
async def test_loop_stops_after_repeated_verifier_failures(isolated_env):
    engine = FakeEngine(FakeVerifierClient([ValueError("bad")] * 5))
    bundle = FakeBundle(engine, isolated_env)
    goal = GoalDefinition(condition="x", max_turns_budget=20, turns_run=1)

    printed = await _run(bundle, goal)

    assert goal.status == "failed"
    assert goal.verifier_failures >= 3
    assert any("verifier failed" in line for line in printed)


@pytest.mark.asyncio
async def test_loop_caps_verifier_timeout_as_failure(isolated_env):
    engine = FakeEngine(SlowVerifierClient(sleep_seconds=2.0))
    bundle = FakeBundle(engine, isolated_env)
    goal = GoalDefinition(condition="verdict is slow", max_turns_budget=20, turns_run=1)

    printed = await _run(bundle, goal, verifier_timeout=0.05)

    assert goal.status == "failed"
    assert goal.verifier_failures == 3
    assert any("verifier failed" in line for line in printed)
    assert any("attempt 2/3" in line for line in printed)


@pytest.mark.asyncio
async def test_loop_verifier_succeeds_within_timeout(isolated_env):
    engine = FakeEngine(SlowVerifierClient(sleep_seconds=0.01))
    bundle = FakeBundle(engine, isolated_env)
    goal = GoalDefinition(condition="quick verdict", max_turns_budget=10)

    printed = await _run(bundle, goal, verifier_timeout=5.0)

    assert goal.status == "completed"
    assert goal.verifier_failures == 0
    assert goal.last_verdict is not None and goal.last_verdict.done
    assert any("verifier judging" in line for line in printed)


@pytest.mark.asyncio
async def test_loop_persists_progress_after_every_turn(isolated_env):
    engine = FakeEngine(FakeVerifierClient([{"done": True}]))
    bundle = FakeBundle(engine, isolated_env)
    goal = GoalDefinition(condition="record me", max_turns_budget=10)

    await _run(bundle, goal)

    stored = GoalStore(isolated_env).load()
    assert stored is not None
    assert stored.status == "completed"
    assert stored.turns_run == 1
    assert bundle.session_backend.snapshots  # session snapshot written


@pytest.mark.asyncio
async def test_loop_survives_inner_max_turns(isolated_env):
    verdicts = [
        {"done": False, "next_step_hint": "try again"},
        {"done": True},
    ]
    engine = FakeEngine(FakeVerifierClient(verdicts))
    engine._fail_next_submit = True  # first submission hits MaxTurnsExceeded
    bundle = FakeBundle(engine, isolated_env)
    goal = GoalDefinition(condition="resilient", max_turns_budget=10)

    await _run(bundle, goal)

    assert goal.status == "completed"


@pytest.mark.asyncio
async def test_loop_does_not_run_when_not_active(isolated_env):
    engine = FakeEngine(FakeVerifierClient([]))
    bundle = FakeBundle(engine, isolated_env)
    goal = GoalDefinition(condition="paused goal", status="paused")

    printed = await _run(bundle, goal)

    assert len(engine.submitted_prompts) == 0
    assert any("nothing to run" in line for line in printed)


@pytest.mark.asyncio
async def test_loop_restores_session_on_resume(isolated_env):
    # Simulate a fresh process: engine starts empty, session snapshot has history.
    engine = FakeEngine(FakeVerifierClient([{"done": True}]))
    engine._messages = []
    bundle = FakeBundle(engine, isolated_env)
    bundle.session_backend._latest_snapshot = {
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "fix the bug"}]},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "tool_1", "name": "bash", "input": {"command": "git status"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tool_1", "content": ".qoder/ ignored"}]},
        ]
    }
    goal = GoalDefinition(condition="fix bug", turns_run=2)

    printed = await _run(bundle, goal)

    # Engine messages restored from snapshot so verifier sees prior evidence.
    assert len(engine.messages) >= 3
    assert goal.status == "completed"
    assert any("Restored" in line and "messages" in line for line in printed)