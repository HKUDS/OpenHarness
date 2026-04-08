"""Recovery and compensation strategies for workflow node failures."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from openharness.workflow.types import NodeResult, NodeStatus, WorkflowNode

log = logging.getLogger(__name__)


@dataclass
class CompensationAction:
    """A compensation action to run after a node failure."""

    name: str
    """Human-readable name for logging."""

    prompt: str
    """Prompt for the compensating agent."""

    tools: list[str] = field(default_factory=list)
    """Tools available to the compensating agent."""


class RecoveryManager:
    """
    Manages node failure recovery with retry and compensation strategies.

    Responsibilities:
    - Decide whether to retry a failed node based on retry policy
    - Execute compensation actions for irreversible failures
    - Determine if downstream nodes should be skipped or can continue
    """

    def __init__(
        self,
        compensation_actions: dict[str, CompensationAction] | None = None,
    ) -> None:
        """
        Initialize the RecoveryManager.

        Args:
            compensation_actions: Optional map from node ID to compensation action.
        """
        self._compensations = compensation_actions or {}

    def should_retry(
        self,
        node: WorkflowNode,
        result: NodeResult,
        current_attempt: int,
    ) -> bool:
        """
        Determine if a failed node should be retried.

        Args:
            node: The failed workflow node.
            result: The failed execution result.
            current_attempt: Number of attempts already made (1-based).

        Returns:
            True if the node should be retried.
        """
        if current_attempt >= node.retry_policy.max_attempts:
            return False

        if result.status != NodeStatus.FAILED:
            return False

        # Check if the error matches a retryable exception
        retryable = node.retry_policy.retryable_exceptions
        if retryable and result.error_message:
            # Simple string matching for now; could be enhanced with exception types
            for exc_name in retryable:
                if exc_name in result.error_message:
                    return True
            # None of the specified exceptions match
            return False

        # No filter specified, retry all failures
        return True

    def get_compensation_action(self, node_id: str) -> CompensationAction | None:
        """
        Get a compensation action for a failed node, if one is registered.

        Args:
            node_id: The ID of the failed node.

        Returns:
            CompensationAction if registered, None otherwise.
        """
        return self._compensations.get(node_id)

    def should_skip_downstream(
        self,
        failed_node_id: str,
        downstream_ids: list[str],
        dag: object,  # WorkflowDAG (avoid circular import)
    ) -> list[str]:
        """
        Determine which downstream nodes should be skipped due to a failure.

        Nodes that depend on a failed node (and the failed node has
        continue_on_failure=False) should be skipped transitively.

        Args:
            failed_node_id: The ID of the failed node.
            downstream_ids: IDs of nodes that directly depend on the failed node.
            dag: The WorkflowDAG for transitive dependency analysis.

        Returns:
            List of node IDs that should be skipped.
        """
        # This is handled by the scheduler via continue_on_failure flag,
        # but we provide this method for external orchestration if needed.
        return []

    async def execute_compensation(
        self,
        action: CompensationAction,
        run_agent: Callable[[str, list[str]], NodeResult],
    ) -> NodeResult:
        """
        Execute a compensation action through the agent loop.

        Args:
            action: The compensation action to execute.
            run_agent: Callable that runs an agent with a prompt and tool list.

        Returns:
            Result of the compensation action.
        """
        log.info("Executing compensation: %s", action.name)
        try:
            result = await run_agent(action.prompt, action.tools)
            result.metadata["compensation"] = action.name
            return result
        except Exception as exc:
            log.exception("Compensation '%s' failed: %s", action.name, exc)
            return NodeResult(
                node_id=f"compensation:{action.name}",
                status=NodeStatus.FAILED,
                error_message=f"Compensation failed: {exc}",
                metadata={"compensation": action.name},
            )


def build_default_recovery_manager() -> RecoveryManager:
    """
    Build a RecoveryManager with sensible default compensation actions.

    Currently returns an empty manager; extend as needed.
    """
    return RecoveryManager()
