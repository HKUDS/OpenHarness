"""Goal-driven autonomy data models.

These models back the ``/goal`` slash command: a completion condition the
main model pursues over many turns, with a lightweight verifier model
judging continue/done after each turn.
"""

from __future__ import annotations

import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field

GoalStatus = Literal["active", "paused", "completed", "failed", "cancelled"]


class VerifierVerdict(BaseModel):
    """Structured verdict returned by the goal verifier model."""

    done: bool = False
    confidence: float = 0.0
    rationale: str = ""
    next_step_hint: str = ""
    progress_summary: str = ""


class GoalDefinition(BaseModel):
    """Persistent definition and runtime state of one ``/goal``."""

    goal_id: str = Field(default_factory=lambda: f"goal_{uuid.uuid4().hex[:8]}")
    condition: str
    verifier_model: str = ""
    max_turns_budget: int = 100
    max_tokens_budget: int | None = None
    turns_run: int = 0
    tokens_used: int = 0
    verifier_failures: int = 0
    last_verdict: VerifierVerdict | None = None
    next_step_hint: str = ""
    status: GoalStatus = "active"
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def touch(self) -> None:
        """Refresh the updated-at timestamp."""
        self.updated_at = time.time()

    def budget_exhausted(self, total_tokens: int) -> bool:
        """Return whether the turn or token budget has been exhausted."""
        if self.turns_run >= self.max_turns_budget:
            return True
        if self.max_tokens_budget is not None and total_tokens >= self.max_tokens_budget:
            return True
        return False