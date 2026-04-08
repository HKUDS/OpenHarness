"""Tests for workflow tracing and observability (trace.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openharness.workflow.trace import WorkflowTracer
from openharness.workflow.types import (
    NodeResult,
    NodeStatus,
    WorkflowDAG,
    WorkflowNode,
)


@pytest.fixture
def sample_dag() -> WorkflowDAG:
    return WorkflowDAG(
        name="test-dag",
        description="A test workflow",
        nodes=[
            WorkflowNode(id="a", prompt_template="step a"),
            WorkflowNode(id="b", prompt_template="step b", depends_on=["a"]),
        ],
    )


@pytest.fixture
def sample_results() -> dict[str, NodeResult]:
    return {
        "a": NodeResult(
            node_id="a",
            status=NodeStatus.COMPLETED,
            output="Output from A",
            input_tokens=100,
            output_tokens=50,
            duration_seconds=2.5,
        ),
        "b": NodeResult(
            node_id="b",
            status=NodeStatus.FAILED,
            output="Output from B",
            error_message="Something went wrong",
            input_tokens=80,
            output_tokens=30,
            duration_seconds=1.2,
        ),
    }


class TestWorkflowTracer:
    def test_export_json(self, tmp_path: Path, sample_dag: WorkflowDAG, sample_results: dict) -> None:
        tracer = WorkflowTracer(output_dir=tmp_path)
        output_path = tracer.export_json(sample_dag, sample_results)

        assert output_path.exists()
        assert output_path.suffix == ".json"

        data = json.loads(output_path.read_text())
        assert data["workflow"]["name"] == "test-dag"
        assert data["execution"]["total_nodes"] == 2
        assert "a" in data["nodes"]
        assert "b" in data["nodes"]
        assert data["nodes"]["a"]["status"] == "completed"
        assert data["nodes"]["b"]["status"] == "failed"

    def test_export_graphviz(self, tmp_path: Path, sample_dag: WorkflowDAG, sample_results: dict) -> None:
        tracer = WorkflowTracer(output_dir=tmp_path)
        output_path = tracer.export_graphviz(sample_dag, sample_results)

        assert output_path.exists()
        assert output_path.suffix == ".dot"

        content = output_path.read_text()
        assert "digraph Workflow" in content
        assert '"a"' in content
        assert '"b"' in content
        assert '"a" -> "b"' in content

    def test_export_html_report(self, tmp_path: Path, sample_dag: WorkflowDAG, sample_results: dict) -> None:
        tracer = WorkflowTracer(output_dir=tmp_path)
        output_path = tracer.export_html_report(sample_dag, sample_results)

        assert output_path.exists()
        assert output_path.suffix == ".html"

        content = output_path.read_text()
        assert "<!DOCTYPE html>" in content
        assert "test-dag" in content
        assert "completed" in content.lower()
        assert "failed" in content.lower()

    def test_last_export_path(self, tmp_path: Path, sample_dag: WorkflowDAG, sample_results: dict) -> None:
        tracer = WorkflowTracer(output_dir=tmp_path)
        tracer.export_json(sample_dag, sample_results)

        assert tracer.last_export_path is not None
        assert tracer.last_export_path.exists()

    def test_export_without_output_dir_raises_error(self, sample_dag: WorkflowDAG, sample_results: dict) -> None:
        tracer = WorkflowTracer()

        with pytest.raises(ValueError, match="No output directory"):
            tracer.export_json(sample_dag, sample_results)

        with pytest.raises(ValueError, match="No output directory"):
            tracer.export_graphviz(sample_dag, sample_results)

    def test_custom_output_path(self, tmp_path: Path, sample_dag: WorkflowDAG, sample_results: dict) -> None:
        tracer = WorkflowTracer()
        custom_path = tmp_path / "custom-trace.json"

        output = tracer.export_json(sample_dag, sample_results, output_path=custom_path)
        assert output == custom_path
        assert custom_path.exists()
