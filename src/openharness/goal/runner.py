"""Goal runner: the outer autonomy loop driving the engine toward a goal.

Layout of one goal session:

    first turn (condition) -> [ budget check -> verifier -> continue? ]*
    -> completed / failed

The loop is hosted by the interactive runtime so every turn renders as a
normal conversation turn. Progress is persisted to the goal store and the
session snapshot after every turn, so a killed process resumes cleanly
with ``/goal resume``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Awaitable, Callable

from openharness.engine.messages import (
    ConversationMessage,
    sanitize_conversation_messages,
)
from openharness.engine.query import MaxTurnsExceeded
from openharness.goal.prompts import (
    DEFAULT_CONTINUE_PROMPT,
    MAX_VERIFIER_PARSE_FAILURES,
    build_goal_system_block,
)
from openharness.goal.store import GoalStore
from openharness.goal.types import GoalDefinition
from openharness.goal.verifier import run_goal_verifier

if TYPE_CHECKING:
    from openharness.ui.runtime import RuntimeBundle

log = logging.getLogger(__name__)

# Hard cap for a verifier judgement: flash-scale models answer in seconds, so
# anything beyond this means the upstream hung and we should count a failure
# instead of leaving the UI stuck in the busy state forever.
VERIFIER_TIMEOUT_SECONDS = 60.0

SystemPrinter = Callable[[str], Awaitable[None]]
StreamRenderer = Callable[[object], Awaitable[None]]


async def _submit_turn(engine, prompt: str, render_event: StreamRenderer) -> bool:
    """Run one engine turn, returning False when the inner loop hit max_turns."""
    try:
        async for event in engine.submit_message(prompt):
            await render_event(event)
    except MaxTurnsExceeded:
        return False
    return True


async def _save_progress(goal_store: GoalStore, goal: GoalDefinition) -> None:
    goal_store.save(goal)


async def run_goal_loop(
    bundle: "RuntimeBundle",
    goal: GoalDefinition,
    render_event: StreamRenderer,
    print_system: SystemPrinter,
    *,
    verifier_timeout: float = VERIFIER_TIMEOUT_SECONDS,
) -> None:
    """Drive the engine toward ``goal`` until done or budget exhausted."""
    engine = bundle.engine
    settings = bundle.current_settings()
    goal_store = GoalStore(bundle.cwd)

    if goal.status != "active":
        await print_system(f"Goal is {goal.status}, nothing to run.")
        return

    # When resuming a goal in a fresh process the engine has no conversation
    # history, so the verifier would judge against an empty transcript and
    # always say "no evidence".  Restore the latest session snapshot so the
    # judge can see the tool calls/results that already happened.
    if goal.turns_run > 0 and len(engine.messages) < 3:
        snapshot = bundle.session_backend.load_latest(bundle.cwd)
        if snapshot and snapshot.get("messages"):
            try:
                restored = sanitize_conversation_messages(
                    [ConversationMessage.model_validate(m) for m in snapshot["messages"]]
                )
                if restored:
                    engine.load_messages(restored)
                    await print_system(
                        f"[goal] Restored {len(restored)} messages from the "
                        "session snapshot so the verifier can see prior evidence."
                    )
            except Exception as exc:
                log.warning("Failed to restore session for goal resume: %s", exc)

    if bundle.enforce_max_turns:
        engine.set_max_turns(settings.max_turns)

    # Keep the goal in view for the main model (Codex-style).
    engine.set_system_prompt(
        engine.system_prompt + build_goal_system_block(goal.condition)
    )
    await print_system(f"[goal] x{goal.turns_run} Active goal: {goal.condition}")

    try:
        # First turn executes the completion condition directly, skipping
        # the verifier so the agent starts working instead of judging.
        if goal.turns_run == 0:
            await _submit_turn(engine, goal.condition, render_event)
            goal.turns_run = 1
            goal.tokens_used = engine.total_usage.total_tokens
            await _save_progress(goal_store, goal)
            await bundle.session_backend.save_snapshot(
                cwd=bundle.cwd,
                model=settings.model,
                system_prompt=engine.system_prompt,
                messages=engine.messages,
                usage=engine.total_usage,
                session_id=bundle.session_id,
                tool_metadata=engine.tool_metadata,
            )

        while goal.status == "active":
            # Budget checks take priority over any further model calls.
            if goal.budget_exhausted(engine.total_usage.total_tokens):
                goal.status = "failed"
                await _save_progress(goal_store, goal)
                await print_system(
                    f"[goal] Budget exhausted after {goal.turns_run} turns "
                    f"({engine.total_usage.total_tokens} tokens). "
                    "Run /goal resume to raise the budget or continue."
                )
                break

            try:
                await print_system("[goal] verifier judging progress...")
                verdict = await asyncio.wait_for(
                    run_goal_verifier(
                        engine.api_client,
                        goal,
                        engine.messages,
                        fallback_model=engine.model,
                    ),
                    timeout=verifier_timeout,
                )
                goal.verifier_failures = 0
                goal.last_verdict = verdict
                goal.next_step_hint = verdict.next_step_hint
            except Exception as exc:
                goal.verifier_failures += 1
                log.warning("Goal verifier failed: %s", exc)
                goal.last_verdict = None
                if goal.verifier_failures >= MAX_VERIFIER_PARSE_FAILURES:
                    goal.status = "failed"
                    await _save_progress(goal_store, goal)
                    await print_system(
                        f"[goal] Stopped: verifier failed "
                        f"{goal.verifier_failures} times in a row."
                    )
                    break
                # Keep working with a safe, deterministic nudge.
                goal.next_step_hint = DEFAULT_CONTINUE_PROMPT
                await print_system(
                    "[goal] verifier unavailable "
                    f"(attempt {goal.verifier_failures}/"
                    f"{MAX_VERIFIER_PARSE_FAILURES}), continuing."
                )

            if goal.last_verdict is not None and goal.last_verdict.done:
                goal.status = "completed"
                goal.next_step_hint = ""
                await _save_progress(goal_store, goal)
                summary = goal.last_verdict.progress_summary or goal.last_verdict.rationale
                await print_system(
                    f"[goal] Completed after {goal.turns_run} turns"
                    + (f": {summary}" if summary else "")
                )
                break

            hint = goal.next_step_hint.strip() or DEFAULT_CONTINUE_PROMPT
            if goal.last_verdict is not None and goal.last_verdict.rationale:
                await print_system(f"[goal] continue — {goal.last_verdict.rationale}")
            await _submit_turn(engine, hint, render_event)
            goal.turns_run += 1
            goal.tokens_used = engine.total_usage.total_tokens
            await _save_progress(goal_store, goal)
            await bundle.session_backend.save_snapshot(
                cwd=bundle.cwd,
                model=settings.model,
                system_prompt=engine.system_prompt,
                messages=engine.messages,
                usage=engine.total_usage,
                session_id=bundle.session_id,
                tool_metadata=engine.tool_metadata,
            )
    finally:
        await _save_progress(goal_store, goal)