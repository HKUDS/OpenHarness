"""Tests for DAG scheduler (scheduler.py)."""

from __future__ import annotations


import pytest

from openharness.workflow.scheduler import DAGScheduler
from openharness.workflow.types import NodeResult, NodeStatus, WorkflowDAG, WorkflowNode


@pytest.fixture
def linear_dag() -> WorkflowDAG:
    return WorkflowDAG(
        name="linear-test",
        nodes=[
            WorkflowNode(id="a", prompt_template="step a"),
            WorkflowNode(id="b", prompt_template="step b", depends_on=["a"]),
            WorkflowNode(id="c", prompt_template="step c", depends_on=["b"]),
        ],
    )


@pytest.fixture
def parallel_dag() -> WorkflowDAG:
    return WorkflowDAG(
        name="parallel-test",
        nodes=[
            WorkflowNode(id="root", prompt_template="root"),
            WorkflowNode(id="left", prompt_template="left", depends_on=["root"]),
            WorkflowNode(id="right", prompt_template="right", depends_on=["root"]),
            WorkflowNode(id="merge", prompt_template="merge", depends_on=["left", "right"]),
        ],
    )


class TestDAGScheduler:
    @pytest.mark.asyncio
    async def test_execute_linear_dag(self, linear_dag: WorkflowDAG) -> None:
        call_order = []

        async def mock_run_node(node, upstream):
            call_order.append(node.id)
            return NodeResult(node_id=node.id, status=NodeStatus.COMPLETED, output=f"output-{node.id}")

        scheduler = DAGScheduler(linear_dag)
        results = await scheduler.execute_all(mock_run_node)

        assert call_order == ["a", "b", "c"]
        assert len(results) == 3
        assert all(r.status == NodeStatus.COMPLETED for r in results.values())

    @pytest.mark.asyncio
    async def test_execute_parallel_dag(self, parallel_dag: WorkflowDAG) -> None:
        async def mock_run_node(node, upstream):
            return NodeResult(node_id=node.id, status=NodeStatus.COMPLETED, output=f"output-{node.id}")

        scheduler = DAGScheduler(parallel_dag)
        results = await scheduler.execute_all(mock_run_node)

        assert len(results) == 4
        assert "root" in results
        assert "left" in results
        assert "right" in results
        assert "merge" in results

    @pytest.mark.asyncio
    async def test_node_failure_propagation(self, linear_dag: WorkflowDAG) -> None:
        async def mock_run_node(node, upstream):
            if node.id == "b":
                return NodeResult(
                    node_id=node.id,
                    status=NodeStatus.FAILED,
                    error_message="Intentional failure",
                )
            return NodeResult(node_id=node.id, status=NodeStatus.COMPLETED)

        scheduler = DAGScheduler(linear_dag)
        results = await scheduler.execute_all(mock_run_node)

        assert results["a"].status == NodeStatus.COMPLETED
        assert results["b"].status == NodeStatus.FAILED
        assert results["b"].error_message == "Intentional failure"
        # Node c should not execute because b failed
        assert "c" not in results or results["c"].status != NodeStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_get_summary(self, linear_dag: WorkflowDAG) -> None:
        async def mock_run_node(node, upstream):
            return NodeResult(
                node_id=node.id,
                status=NodeStatus.COMPLETED,
                input_tokens=100,
                output_tokens=50,
                duration_seconds=1.5,
            )

        scheduler = DAGScheduler(linear_dag)
        await scheduler.execute_all(mock_run_node)
        summary = scheduler.get_summary()

        assert summary["workflow_name"] == "linear-test"
        assert summary["total_nodes"] == 3
        assert summary["completed"] == 3
        assert summary["failed"] == 0
        assert summary["total_tokens"] == 450  # 3 * (100 + 50)
