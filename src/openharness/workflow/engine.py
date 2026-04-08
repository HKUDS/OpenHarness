"""High-level WorkflowEngine: unified entry point for workflow execution."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, AsyncIterator

from openharness.engine.query import QueryContext

from openharness.workflow.executor import NodeExecutor
from openharness.workflow.scheduler import DAGScheduler
from openharness.workflow.trace import WorkflowTracer
from openharness.workflow.types import NodeResult, NodeStatus, WorkflowDAG, WorkflowNode

log = logging.getLogger(__name__)


class WorkflowEngine:
    """
    Top-level engine for executing workflow DAGs.

    Coordinates scheduling, node execution (via the Agent Loop), recovery,
    and tracing into a single unified interface.
    """

    def __init__(
        self,
        query_context: QueryContext,
        output_dir: Path | None = None,
    ) -> None:
        """
        Initialize the WorkflowEngine.

        Args:
            query_context: Shared query context for all nodes.
            output_dir: Optional directory for trace output (JSON/Graphviz).
        """
        self._query_context = query_context
        self._output_dir = output_dir
        self._tracer = WorkflowTracer(output_dir) if output_dir else None
        self._executor = NodeExecutor(query_context)

    async def execute(
        self,
        dag: WorkflowDAG,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, NodeResult]:
        """
        Execute a complete workflow DAG.

        Args:
            dag: The workflow definition to execute.
            variables: Optional global variables for prompt interpolation.

        Returns:
            Dictionary mapping node IDs to their execution results.

        Raises:
            ValueError: If the DAG contains a cycle.
        """
        # Validate structure
        order = dag.validate_execution_order()
        if order is None:
            raise ValueError(f"Workflow DAG '{dag.name}' contains a cycle, cannot execute")

        log.info(
            "Starting workflow '%s': %d nodes, execution order: %s",
            dag.name,
            len(dag.nodes),
            order,
        )

        scheduler = DAGScheduler(dag)

        async def _run_node(
            node: WorkflowNode,
            upstream_results: dict[str, NodeResult],
        ) -> NodeResult:
            """Execute a single node with retry logic."""
            return await self._execute_with_retry(node, upstream_results, variables)

        results = await scheduler.execute_all(_run_node)

        # Trace execution
        if self._tracer is not None:
            trace_path = self._tracer.export_json(dag, results)
            log.info("Workflow trace exported to: %s", trace_path)

        # Log summary
        summary = scheduler.get_summary()
        log.info("Workflow '%s' completed: %s", dag.name, summary)

        return results

    async def execute_stream(
        self,
        dag: WorkflowDAG,
        variables: dict[str, Any] | None = None,
    ) -> AsyncIterator[tuple[str, NodeResult]]:
        """
        Execute a workflow DAG and yield results as nodes complete.

        Args:
            dag: The workflow definition to execute.
            variables: Optional global variables for prompt interpolation.

        Yields:
            (node_id, NodeResult) as each node completes.
        """
        order = dag.validate_execution_order()
        if order is None:
            raise ValueError(f"Workflow DAG '{dag.name}' contains a cycle, cannot execute")

        scheduler = DAGScheduler(dag)

        async def _run_node(
            node: WorkflowNode,
            upstream_results: dict[str, NodeResult],
        ) -> NodeResult:
            return await self._execute_with_retry(node, upstream_results, variables)

        async for node_id, result in scheduler.execute_stream(_run_node):
            yield (node_id, result)

    async def _execute_with_retry(
        self,
        node: WorkflowNode,
        upstream_results: dict[str, NodeResult],
        global_variables: dict[str, Any] | None,
    ) -> NodeResult:
        """
        Execute a node with automatic retry logic.

        If the node fails and has a retry policy, it will be re-executed
        up to max_attempts times with exponential backoff.
        """
        last_result: NodeResult | None = None

        for attempt in range(node.retry_policy.max_attempts):
            if attempt > 0:
                delay = node.retry_policy.delay_for_attempt(attempt)
                log.info(
                    "Retrying node '%s' (attempt %d/%d), waiting %.1fs",
                    node.id,
                    attempt + 1,
                    node.retry_policy.max_attempts,
                    delay,
                )
                await asyncio.sleep(delay)

            last_result = await self._executor.execute(
                node,
                upstream_results,
                global_variables,
            )

            if last_result.status == NodeStatus.COMPLETED:
                last_result.attempts = attempt + 1
                return last_result

            # Node failed, check if we should retry
            log.warning(
                "Node '%s' failed (attempt %d/%d): %s",
                node.id,
                attempt + 1,
                node.retry_policy.max_attempts,
                last_result.error_message,
            )

        # All retries exhausted
        if last_result is not None:
            last_result.attempts = node.retry_policy.max_attempts
            if node.continue_on_failure:
                last_result.status = NodeStatus.SKIPPED
                log.info(
                    "Node '%s' failed but continue_on_failure=True, marking as SKIPPED",
                    node.id,
                )
            return last_result

        # Should never reach here, but handle gracefully
        return NodeResult(
            node_id=node.id,
            status=NodeStatus.FAILED,
            error_message="Unknown execution failure",
            attempts=node.retry_policy.max_attempts,
        )

    def get_trace_path(self) -> Path | None:
        """Return the path where the last trace was exported, if available."""
        return self._tracer.last_export_path if self._tracer else None
