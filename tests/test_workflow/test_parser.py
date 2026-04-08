"""Tests for YAML workflow parser (parser.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.workflow.parser import (
    get_builtin_templates_dir,
    list_builtin_templates,
    load_builtin_template,
    load_workflow,
)


VALID_WORKFLOW_YAML = """
name: test-workflow
description: "A test workflow"
version: "1.2.3"
variables:
  target: "/src"

nodes:
  - id: analyze
    type: reviewer
    prompt: "Analyze the code at ${target}"
    retry:
      max_attempts: 2
    timeout_seconds: 120

  - id: implement
    type: coder
    depends_on:
      - analyze
    prompt: "Implement fixes based on: ${analyze_output}"
    tools:
      - read_file
      - write_file
    continue_on_failure: false
    variables:
      feature: auth
"""


class TestLoadWorkflow:
    def test_load_from_yaml_string(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "workflow.yaml"
        yaml_file.write_text(VALID_WORKFLOW_YAML)

        dag = load_workflow(yaml_file)

        assert dag.name == "test-workflow"
        assert dag.description == "A test workflow"
        assert dag.version == "1.2.3"
        assert dag.variables == {"target": "/src"}
        assert len(dag.nodes) == 2

    def test_node_parsing(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "workflow.yaml"
        yaml_file.write_text(VALID_WORKFLOW_YAML)
        dag = load_workflow(yaml_file)

        analyze = dag.node_map["analyze"]
        assert analyze.agent_type == "reviewer"
        assert "Analyze the code" in analyze.prompt_template
        assert analyze.retry_policy.max_attempts == 2
        assert analyze.timeout_seconds == 120

        implement = dag.node_map["implement"]
        assert implement.agent_type == "coder"
        assert implement.depends_on == ["analyze"]
        assert implement.tools == ["read_file", "write_file"]
        assert implement.continue_on_failure is False
        assert implement.variables == {"feature": "auth"}

    def test_load_from_string(self) -> None:
        dag = load_workflow(VALID_WORKFLOW_YAML)
        assert dag.name == "test-workflow"

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_workflow("/nonexistent/path/workflow.yaml")

    def test_invalid_yaml(self) -> None:
        with pytest.raises(ValueError, match="must be a mapping"):
            load_workflow("- just a list\n- not a dict")

    def test_missing_nodes(self) -> None:
        with pytest.raises(ValueError, match="must have at least one node"):
            load_workflow("name: empty\nnodes: []")

    def test_node_missing_prompt(self) -> None:
        yaml_str = """
name: bad
nodes:
  - id: no-prompt
"""
        with pytest.raises(ValueError, match="must have a 'prompt'"):
            load_workflow(yaml_str)

    def test_simple_retry_policy(self) -> None:
        yaml_str = """
name: test
nodes:
  - id: a
    prompt: "test"
    retry: 5
"""
        dag = load_workflow(yaml_str)
        assert dag.node_map["a"].retry_policy.max_attempts == 5

    def test_default_retry_policy(self) -> None:
        yaml_str = """
name: test
nodes:
  - id: a
    prompt: "test"
"""
        dag = load_workflow(yaml_str)
        assert dag.node_map["a"].retry_policy.max_attempts == 3


class TestBuiltinTemplates:
    def test_templates_dir_exists(self) -> None:
        templates_dir = get_builtin_templates_dir()
        assert templates_dir.exists()

    def test_list_templates(self) -> None:
        templates = list_builtin_templates()
        assert len(templates) > 0
        assert "refactor" in templates
        assert "feature-dev" in templates

    def test_load_refactor_template(self) -> None:
        dag = load_builtin_template("refactor")
        assert dag.name == "code-refactor"
        assert len(dag.nodes) == 3
        assert dag.node_map["code-analysis"] is not None

    def test_load_feature_dev_template(self) -> None:
        dag = load_builtin_template("feature-dev")
        assert dag.name == "feature-dev"
        assert len(dag.nodes) == 5

    def test_load_test_and_docs_template(self) -> None:
        dag = load_builtin_template("test-and-docs")
        assert dag.name == "test-and-docs"
        assert len(dag.nodes) == 4

    def test_load_nonexistent_template(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            load_builtin_template("nonexistent-template")
