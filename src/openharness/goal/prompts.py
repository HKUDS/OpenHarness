"""Prompt templates for the goal verifier and goal context injection."""

from __future__ import annotations

VERIFIER_SYSTEM_PROMPT = """You are a goal verifier for an autonomous coding agent.

The agent has been working toward a goal defined by the user. You decide
whether the goal has been achieved. Judge strictly: the completion
condition must be satisfied by real evidence (tests passing, code written,
results produced) — do not accept an agent's mere claim of completion.

Respond with a single JSON object only, no commentary, shaped like:

{"done": false, "confidence": 0.0, "rationale": "...",
 "next_step_hint": "...", "progress_summary": "..."}

- "done": true only when the completion condition is satisfied.
- "confidence": 0.0-1.0, your confidence in the verdict.
- "rationale": short reason for the verdict (1-3 sentences).
- "next_step_hint": when "done" is false, a specific instruction for the
  agent's next step; empty when done.
- "progress_summary": one sentence describing progress so far.
"""

VERIFIER_INPUT_TEMPLATE = """Goal (completion condition):
{condition}

Recent conversation:
{transcript}

Judge whether the goal is achieved. Output only a JSON object with the
keys "done", "confidence", "rationale", "next_step_hint", and
"progress_summary" — no other text."""

#: Fallback instruction used when the verifier returns a continue verdict
#: without a usable next-step hint.
DEFAULT_CONTINUE_PROMPT = (
    "Continue working toward the goal. Report concrete progress and verify "
    "your work with real evidence (tests, commands, file contents)."
)

GOAL_SYSTEM_BLOCK_TEMPLATE = """

## Active Goal (set via /goal)

{condition}

You are pursuing this goal autonomously. Work step by step and verify your
own work with real evidence (run tests, inspect files, execute commands)
before considering the goal complete. The goal is complete only when the
completion condition above is fully satisfied.
"""

MAX_TRANSCRIPT_MESSAGES = 24
MAX_BLOCK_CHARS = 500

MAX_VERIFIER_PARSE_FAILURES = 3


def build_verifier_prompt(goal_condition: str, transcript: str) -> str:
    """Render the verifier input prompt for one judgement call."""
    return VERIFIER_INPUT_TEMPLATE.format(
        condition=goal_condition,
        transcript=transcript.strip() or "(no conversation yet)",
    )


def build_goal_system_block(condition: str) -> str:
    """Render the goal context block injected into the main system prompt."""
    return GOAL_SYSTEM_BLOCK_TEMPLATE.format(condition=condition)