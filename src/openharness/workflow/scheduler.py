"""DAG scheduler for workflow orchestration."""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Callable

from openharness.workflow.types import NodeResult, NodeStatus, WorkflowDAG, WorkflowNode

log = logging.getLogger(__name__)

NodeExecutor = object  # Forward reference, actual type in executor.py


class DAGScheduler:
    """Schedules and executes WorkflowDAG nodes respecting dependency order."""

    def __init__(self, dag: WorkflowDAG) -> None:
        self._dag = dag
        self._results: dict[str, NodeResult] = {}
        self._lock = asyncio.Lock()

    @property
    def results(self) -> dict[str, NodeResult]:
        """Read-only access to node execution results."""
        return dict(self._results)

    async def execute_all(
        self,
        run_node: Callable[[WorkflowNode, dict[str, NodeResult]], "asyncio.Task[NodeResult]"],
    ) -> dict[str, NodeResult]:
        """
        Execute all nodes in topological order with parallel layer execution.

        Args:
            run_node: Async callable that executes a single node given its upstream results.
                     Signature: async def run_node(node, upstream_results) -> NodeResult

        Returns:
            Dictionary mapping node IDs to their NodeResult.
        """
        # Validate DAG structure first
        order = self._dag.validate_execution_order()
        if order is None:
            raise ValueError(f"Workflow DAG '{self._dag.name}' contains a cycle, cannot execute")

        layers = self._dag.topological_layers()
        log.info(
            "Executing workflow '%s': %d nodes in %d layers",
            self._dag.name,
            len(self._dag.nodes),
            len(layers),
        )

        for layer_idx, layer in enumerate(layers):
            log.info("Executing layer %d: %s", layer_idx, layer)

            # Filter out nodes that were marked as skipped by failure handling
            active_layer = [nid for nid in layer if nid not in self._results]
            if not active_layer:
                log.info("Layer %d: all nodes skipped, skipping layer", layer_idx)
                continue

            # Gather upstream results for this layer
            upstream = await self._get_upstream_results(active_layer)

            # Execute all nodes in this layer concurrently
            tasks = []
            for node_id in active_layer:
                node = self._dag.node_map[node_id]
                task = asyncio.create_task(
                    run_node(node, upstream),
                    name=f"workflow-node-{node_id}",
                )
                tasks.append((node_id, task))

            # Wait for all tasks in this layer to complete
            for node_id, task in tasks:
                try:
                    result = await task
                    await self._store_result(node_id, result)
                except Exception as exc:
                    log.exception("Node %s execution failed", node_id)
                    result = NodeResult(
                        node_id=node_id,
                        status=NodeStatus.FAILED,
                        error_message=str(exc),
                    )
                    await self._store_result(node_id, result)

            # Check if any node in this layer failed and mark downstream for skipping
            await self._handle_failures()

        return dict(self._results)

    async def execute_stream(
        self,
        run_node: Callable[[WorkflowNode, dict[str, NodeResult]], "asyncio.Task[NodeResult]"],
    ) -> AsyncIterator[tuple[str, NodeResult]]:
        """
        Execute all nodes and yield results as they complete.

        Args:
            run_node: Same as execute_all.

        Yields:
            (node_id, NodeResult) tuples as each node completes.
        """
        layers = self._dag.topological_layers()

        for layer_idx, layer in enumerate(layers):
            log.info("Executing layer %d: %s", layer_idx, layer)

            # Filter out skipped nodes
            active_layer = [nid for nid in layer if nid not in self._results]
            if not active_layer:
                log.info("Layer %d: all nodes skipped, skipping layer", layer_idx)
                continue

            upstream = await self._get_upstream_results(active_layer)

            # Execute concurrently within each layer
            async def _run_and_yield(node_id: str):
                node = self._dag.node_map[node_id]
                try:
                    result = await run_node(node, upstream)
                except Exception as exc:
                    log.exception("Node %s execution failed", node_id)
                    result = NodeResult(
                        node_id=node_id,
                        status=NodeStatus.FAILED,
                        error_message=str(exc),
                    )
                await self._store_result(node_id, result)
                yield (node_id, result)

            # Run all nodes in this layer, yield as they complete
            coros = [_run_and_yield(nid) for nid in active_layer]
            for coro in asyncio.as_completed(coros):
                node_id, result = await coro
                yield (node_id, result)

    async def _get_upstream_results(self, layer: list[str]) -> dict[str, NodeResult]:
        """Collect all upstream results for a given layer."""
        upstream: dict[str, NodeResult] = {}
        async with self._lock:
            for node_id in layer:
                node = self._dag.node_map[node_id]
                for dep_id in node.depends_on:
                    if dep_id in self._results:
                        upstream[dep_id] = self._results[dep_id]
        return upstream

    async def _store_result(self, node_id: str, result: NodeResult) -> None:
        """Store a node result thread-safely."""
        async with self._lock:
            self._results[node_id] = result

    async def _handle_failures(self) -> None:
        """Mark downstream nodes as skipped when upstream nodes fail."""
        async with self._lock:
            # Find all failed nodes
            failed_nodes = [
                nid for nid, r in self._results.items()
                if r.status == NodeStatus.FAILED
            ]
            
            if not failed_nodes:
                return

            # Find all pending nodes and check if their dependencies are met
            for node in self._dag.nodes:
                if node.id in self._results:
                    continue  # Already executed
                
                # Check if any dependency failed
                for dep_id in node.depends_on:
                    if dep_id in self._results and self._results[dep_id].status == NodeStatus.FAILED:
                        # Check if the failed node allows continuation
                        failed_node = self._dag.node_map[dep_id]
                        if not failed_node.continue_on_failure:
                            # Mark this node as skipped
                            self._results[node.id] = NodeResult(
                                node_id=node.id,
                                status=NodeStatus.SKIPPED,
                                error_message=f"Upstream dependency '{dep_id}' failed",
                            )
                            log.info(
                                "Node '%s' skipped due to failed dependency '%s'",
                                node.id,
                                dep_id,
                            )
                            break  # No need to check other dependencies

    def get_summary(self) -> dict[str, object]:
        """Get a summary of workflow execution."""
        total_nodes = len(self._results)
        completed = sum(1 for r in self._results.values() if r.status == NodeStatus.COMPLETED)
        failed = sum(1 for r in self._results.values() if r.status == NodeStatus.FAILED)
        skipped = sum(1 for r in self._results.values() if r.status == NodeStatus.SKIPPED)

        total_tokens = sum(
            r.input_tokens + r.output_tokens
            for r in self._results.values()
        )
        total_duration = sum(r.duration_seconds for r in self._results.values())

        return {
            "workflow_name": self._dag.name,
            "total_nodes": total_nodes,
            "completed": completed,
            "failed": failed,
            "skipped": skipped,
            "total_tokens": total_tokens,
            "total_duration_seconds": round(total_duration, 2),
            "node_details": {
                nid: {
                    "status": r.status.value,
                    "duration_seconds": round(r.duration_seconds, 2),
                    "tokens": r.input_tokens + r.output_tokens,
                    "error": r.error_message,
                }
                for nid, r in self._results.items()
            },
        }
