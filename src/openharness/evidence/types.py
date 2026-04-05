"""Evidence data models for run-level archiving."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4


EvidenceType = Literal[
    "run_start",
    "run_end",
    "task_start",
    "task_progress",
    "task_end",
    "conversation_message",
    "tool_call",
    "tool_result",
    "hook_execution",
    "state_change",
    "performance_metric",
    "error",
]


@dataclass
class EvidenceRecord:
    """Base class for all evidence records."""

    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: float = 0.0
    type: EvidenceType = "run_start"
    run_id: str = ""
    agent_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunEvidence(EvidenceRecord):
    """Evidence for run lifecycle events."""

    session_id: str = ""
    cwd: str = ""
    command_line: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)


@dataclass
class TaskEvidence(EvidenceRecord):
    """Evidence for task execution."""

    task_id: str = ""
    task_type: str = ""
    description: str = ""
    status: str = ""
    command: str = ""
    cwd: str = ""
    output_file: str = ""
    return_code: int | None = None
    duration: float = 0.0
    error_message: str = ""


@dataclass
class ConversationEvidence(EvidenceRecord):
    """Evidence for conversation messages."""

    message_type: str = ""  # "user", "assistant", "system", "tool"
    content: str = ""
    role: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    token_count: int = 0
    model: str = ""


@dataclass
class HookEvidence(EvidenceRecord):
    """Evidence for hook executions."""

    event: str = ""
    hook_type: str = ""
    success: bool = True
    output: str = ""
    blocked: bool = False
    reason: str = ""
    duration: float = 0.0


@dataclass
class StateEvidence(EvidenceRecord):
    """Evidence for application state changes."""

    state_type: str = ""  # "app_state", "task_state", "swarm_state"
    previous_state: dict[str, Any] = field(default_factory=dict)
    new_state: dict[str, Any] = field(default_factory=dict)
    change_reason: str = ""


@dataclass
class PerformanceEvidence(EvidenceRecord):
    """Evidence for performance metrics."""

    metric_name: str = ""
    value: float = 0.0
    unit: str = ""
    category: str = ""  # "cost", "latency", "throughput", "resource"
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorEvidence(EvidenceRecord):
    """Evidence for errors and exceptions."""

    error_type: str = ""
    error_message: str = ""
    traceback: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    recoverable: bool = False