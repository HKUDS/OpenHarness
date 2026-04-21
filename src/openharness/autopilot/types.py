"""Repo autopilot data models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

RepoTaskStatus = Literal[
    "queued",
    "accepted",
    "preparing",
    "running",
    "verifying",
    "pr_open",
    "waiting_ci",
    "repairing",
    "completed",
    "merged",
    "failed",
    "rejected",
    "superseded",
]
RepoTaskSource = Literal[
    "ohmo_request",
    "manual_idea",
    "github_issue",
    "github_pr",
    "claude_code_candidate",
]


class RepoTaskCard(BaseModel):
    """One normalized repo-level work item."""

    id: str
    fingerprint: str
    title: str
    body: str = ""
    source_kind: RepoTaskSource
    source_ref: str = ""
    status: RepoTaskStatus = "queued"
    score: int = 0
    score_reasons: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float
    updated_at: float


class RepoJournalEntry(BaseModel):
    """Append-only repo journal event."""

    timestamp: float
    kind: str
    summary: str
    task_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RepoAutopilotRegistry(BaseModel):
    """Full registry payload."""

    version: int = 1
    updated_at: float = 0.0
    cards: list[RepoTaskCard] = Field(default_factory=list)


class RepoVerificationStep(BaseModel):
    """One verification command result."""

    command: str
    returncode: int
    status: Literal["success", "failed", "skipped", "error"]
    stdout: str = ""
    stderr: str = ""


class RepoRunResult(BaseModel):
    """Result of one autopilot execution attempt."""

    card_id: str
    status: RepoTaskStatus
    assistant_summary: str = ""
    run_report_path: str = ""
    verification_report_path: str = ""
    verification_steps: list[RepoVerificationStep] = Field(default_factory=list)
    attempt_count: int = 0
    worktree_path: str = ""
    pr_number: int | None = None
    pr_url: str = ""
