"""Core data models for workflow DAG orchestration."""

from __future__ import annotations

from collections import defaultdict
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class NodeStatus(str, Enum):
    """Execution status of a workflow node."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class RetryPolicy(BaseModel):
    """Retry configuration for a workflow node."""

    max_attempts: int = Field(default=3, ge=1, le=10)
    """Maximum retry attempts (1-10)."""

    backoff_multiplier: float = Field(default=2.0, ge=1.0)
    """Exponential backoff multiplier."""

    initial_delay_ms: int = Field(default=1000, ge=100)
    """Initial delay in milliseconds."""

    max_delay_ms: int = Field(default=30000, ge=1000)
    """Maximum delay cap in milliseconds."""

    retryable_exceptions: list[str] = Field(default_factory=list)
    """Exception class names that should trigger a retry. Empty = retry all."""

    def delay_for_attempt(self, attempt: int) -> float:
        """Calculate delay for a given attempt using exponential backoff with jitter."""
        import random

        delay = min(
            self.initial_delay_ms * (self.backoff_multiplier ** attempt),
            self.max_delay_ms,
        )
        jitter = random.uniform(0, delay * 0.25)
        return (delay + jitter) / 1000.0  # Convert to seconds


class WorkflowNode(BaseModel):
    """A single node in a workflow DAG."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    """Unique node identifier (lowercase, starts with letter)."""

    agent_type: str = Field(default="general")
    """Agent specialization: general, coder, reviewer, tester, writer, debugger."""

    prompt_template: str
    """Prompt template for this node. Supports {variable} interpolation."""

    tools: list[str] | None = Field(default=None)
    """Tool whitelist for this node. None = inherit from engine defaults."""

    depends_on: list[str] = Field(default_factory=list)
    """Upstream node IDs that must complete before this node runs."""

    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    """Retry configuration for this node."""

    continue_on_failure: bool = Field(default=False)
    """If True, downstream nodes still run even if this node fails."""

    variables: dict[str, Any] = Field(default_factory=dict)
    """Node-specific variables merged into prompt template at runtime."""

    timeout_seconds: int | None = Field(default=None, ge=10)
    """Optional timeout for this node in seconds (minimum 10s)."""

    @field_validator("depends_on")
    @classmethod
    def _no_self_dependency(cls, v: list[str], info) -> list[str]:
        if info.data.get("id") in v:
            raise ValueError("Node cannot depend on itself")
        return v


class NodeResult(BaseModel):
    """Result of executing a workflow node."""

    node_id: str
    status: NodeStatus
    output: str = ""
    """Output text from the agent loop."""

    error_message: str | None = None
    """Error description if status is FAILED."""

    input_tokens: int = 0
    """Token usage for this node."""

    output_tokens: int = 0
    """Token usage for this node."""

    duration_seconds: float = 0.0
    """Wall-clock execution time."""

    attempts: int = 1
    """Number of attempts made (1 = first try succeeded)."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    """Additional metadata (tool calls, intermediate states, etc.)."""


class WorkflowDAG(BaseModel):
    """A complete workflow defined as a directed acyclic graph."""

    name: str = Field(min_length=1, max_length=128)
    """Workflow name for display and logging."""

    description: str = ""
    """Human-readable description."""

    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    """Semantic version string."""

    nodes: list[WorkflowNode] = Field(min_length=1)
    """All nodes in this workflow."""

    variables: dict[str, Any] = Field(default_factory=dict)
    """Global variables available to all nodes via prompt interpolation."""

    @field_validator("nodes")
    @classmethod
    def _unique_node_ids(cls, v: list[WorkflowNode]) -> list[WorkflowNode]:
        ids = [n.id for n in v]
        if len(ids) != len(set(ids)):
            dupes = {x for x in ids if ids.count(x) > 1}
            raise ValueError(f"Duplicate node IDs: {dupes}")
        return v

    @property
    def node_map(self) -> dict[str, WorkflowNode]:
        """Lookup map from node ID to WorkflowNode."""
        return {n.id: n for n in self.nodes}

    @property
    def adjacency(self) -> dict[str, list[str]]:
        """Adjacency list: node ID -> list of downstream node IDs."""
        result: dict[str, list[str]] = defaultdict(list)
        for node in self.nodes:
            if node.id not in result:
                result[node.id] = []
            for dep in node.depends_on:
                result[dep].append(node.id)
        return dict(result)

    @property
    def in_degree(self) -> dict[str, int]:
        """In-degree for each node (number of dependencies)."""
        result: dict[str, int] = {n.id: 0 for n in self.nodes}
        for node in self.nodes:
            result[node.id] = len(node.depends_on)
        return result

    def topological_layers(self) -> list[list[str]]:
        """
        Return nodes grouped into parallel-execution layers via topological sort.

        Each inner list contains node IDs that can run concurrently.
        Layers are ordered so that all dependencies of layer N are in layers < N.

        Raises ValueError if the graph contains a cycle.
        """
        in_deg = dict(self.in_degree)
        layers: list[list[str]] = []
        remaining = set(in_deg.keys())

        while remaining:
            # Find all nodes with zero in-degree among remaining
            layer = [nid for nid in remaining if in_deg[nid] == 0]
            if not layer:
                raise ValueError(
                    f"Cycle detected in workflow DAG. "
                    f"Remaining nodes with unmet dependencies: {remaining}"
                )

            layers.append(sorted(layer))

            # Remove layer nodes and decrease in-degree of their dependents
            for nid in layer:
                remaining.remove(nid)
                # We need the reverse adjacency: for each node, who depends on it?
                # This is stored in depends_on of downstream nodes
                for other_id in list(remaining):
                    other_node = self.node_map[other_id]
                    if nid in other_node.depends_on:
                        in_deg[other_id] -= 1

        return layers

    def validate_execution_order(self) -> list[str] | None:
        """
        Return a valid execution order (flat topological sort), or None if cyclic.
        """
        try:
            layers = self.topological_layers()
            return [nid for layer in layers for nid in layer]
        except ValueError:
            return None
