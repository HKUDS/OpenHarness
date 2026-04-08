"""Tests for workflow data models (types.py)."""

from __future__ import annotations

import pytest

from openharness.workflow.types import (
    NodeResult,
    NodeStatus,
    RetryPolicy,
    WorkflowDAG,
    WorkflowNode,
)


class TestRetryPolicy:
    def test_default_values(self) -> None:
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.backoff_multiplier == 2.0
        assert policy.initial_delay_ms == 1000
        assert policy.max_delay_ms == 30000

    def test_delay_calculation(self) -> None:
        policy = RetryPolicy(
            initial_delay_ms=1000,
            backoff_multiplier=2.0,
            max_delay_ms=10000,
        )
        # Attempt 0: 1000ms + jitter
        delay0 = policy.delay_for_attempt(0)
        assert 1.0 <= delay0 <= 1.25  # 1000ms + up to 25% jitter

        # Attempt 2: 4000ms + jitter (capped at max_delay)
        delay2 = policy.delay_for_attempt(2)
        assert 4.0 <= delay2 <= 5.0  # Should be around 4-5 seconds

    def test_validation(self) -> None:
        with pytest.raises(Exception):  # Pydantic validation error
            RetryPolicy(max_attempts=0)

        with pytest.raises(Exception):
            RetryPolicy(backoff_multiplier=0.5)


class TestWorkflowNode:
    def test_minimal_node(self) -> None:
        node = WorkflowNode(
            id="test-node",
            prompt_template="Do something",
        )
        assert node.id == "test-node"
        assert node.agent_type == "general"
        assert node.depends_on == []
        assert node.tools is None

    def test_full_node(self) -> None:
        node = WorkflowNode(
            id="coder",
            agent_type="coder",
            prompt_template="Write code for ${feature}",
            tools=["read_file", "write_file"],
            depends_on=["planning"],
            continue_on_failure=True,
            variables={"feature": "auth"},
            timeout_seconds=300,
        )
        assert node.agent_type == "coder"
        assert len(node.tools) == 2
        assert node.depends_on == ["planning"]
        assert node.continue_on_failure is True
        assert node.variables == {"feature": "auth"}
        assert node.timeout_seconds == 300

    def test_self_dependency_rejected(self) -> None:
        with pytest.raises(ValueError, match="cannot depend on itself"):
            WorkflowNode(
                id="node-a",
                prompt_template="test",
                depends_on=["node-a"],
            )

    def test_invalid_id_format(self) -> None:
        with pytest.raises(Exception):  # Pydantic pattern validation
            WorkflowNode(
                id="Invalid-ID",
                prompt_template="test",
            )


class TestWorkflowDAG:
    def test_simple_linear_dag(self) -> None:
        dag = WorkflowDAG(
            name="linear",
            nodes=[
                WorkflowNode(id="a", prompt_template="step 1"),
                WorkflowNode(id="b", prompt_template="step 2", depends_on=["a"]),
                WorkflowNode(id="c", prompt_template="step 3", depends_on=["b"]),
            ],
        )
        order = dag.validate_execution_order()
        assert order == ["a", "b", "c"]

        layers = dag.topological_layers()
        assert layers == [["a"], ["b"], ["c"]]

    def test_parallel_dag(self) -> None:
        dag = WorkflowDAG(
            name="parallel",
            nodes=[
                WorkflowNode(id="root", prompt_template="start"),
                WorkflowNode(id="left", prompt_template="left", depends_on=["root"]),
                WorkflowNode(id="right", prompt_template="right", depends_on=["root"]),
                WorkflowNode(id="merge", prompt_template="merge", depends_on=["left", "right"]),
            ],
        )
        layers = dag.topological_layers()
        assert layers == [["root"], ["left", "right"], ["merge"]]

    def test_duplicate_node_ids_rejected(self) -> None:
        with pytest.raises(ValueError, match="Duplicate node IDs"):
            WorkflowDAG(
                name="dupes",
                nodes=[
                    WorkflowNode(id="a", prompt_template="first"),
                    WorkflowNode(id="a", prompt_template="second"),
                ],
            )

    def test_cycle_detection(self) -> None:
        dag = WorkflowDAG(
            name="cyclic",
            nodes=[
                WorkflowNode(id="a", prompt_template="a", depends_on=["b"]),
                WorkflowNode(id="b", prompt_template="b", depends_on=["a"]),
            ],
        )
        order = dag.validate_execution_order()
        assert order is None

        with pytest.raises(ValueError, match="Cycle detected"):
            dag.topological_layers()

    def test_node_map(self) -> None:
        dag = WorkflowDAG(
            name="test",
            nodes=[
                WorkflowNode(id="x", prompt_template="x"),
                WorkflowNode(id="y", prompt_template="y"),
            ],
        )
        assert "x" in dag.node_map
        assert "y" in dag.node_map
        assert dag.node_map["x"].id == "x"

    def test_adjacency_list(self) -> None:
        dag = WorkflowDAG(
            name="test",
            nodes=[
                WorkflowNode(id="a", prompt_template="a"),
                WorkflowNode(id="b", prompt_template="b", depends_on=["a"]),
                WorkflowNode(id="c", prompt_template="c", depends_on=["a"]),
            ],
        )
        adj = dag.adjacency
        assert "a" in adj
        assert "b" in adj["a"]
        assert "c" in adj["a"]


class TestNodeResult:
    def test_default_result(self) -> None:
        result = NodeResult(node_id="test", status=NodeStatus.PENDING)
        assert result.output == ""
        assert result.error_message is None
        assert result.input_tokens == 0
        assert result.attempts == 1

    def test_failed_result(self) -> None:
        result = NodeResult(
            node_id="test",
            status=NodeStatus.FAILED,
            error_message="Something went wrong",
            duration_seconds=5.5,
        )
        assert result.status == NodeStatus.FAILED
        assert result.error_message == "Something went wrong"
        assert result.duration_seconds == 5.5
