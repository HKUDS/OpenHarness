"""YAML workflow definition parser."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from openharness.workflow.types import RetryPolicy, WorkflowDAG, WorkflowNode

log = logging.getLogger(__name__)


def load_workflow(source: str | Path) -> WorkflowDAG:
    """
    Load a WorkflowDAG from a YAML file or YAML string.

    Args:
        source: Path to YAML file, or a YAML string.

    Returns:
        Parsed WorkflowDAG object.

    Raises:
        FileNotFoundError: If source is a path and the file doesn't exist.
        ValueError: If the YAML structure is invalid.
    """
    # First, try to parse as YAML to check if it's content or a path
    # If the string contains newlines or YAML markers, treat as content
    if isinstance(source, str) and ("\n" in source or ":" in source):
        yaml_content = source
    elif isinstance(source, Path):
        if not source.exists():
            raise FileNotFoundError(f"Workflow file not found: {source}")
        yaml_content = source.read_text(encoding="utf-8")
    elif isinstance(source, str):
        path = Path(source)
        if path.exists():
            yaml_content = path.read_text(encoding="utf-8")
        elif source.startswith(("/", "./", "../")) or (source.endswith((".yaml", ".yml")) and "/" in source):
            raise FileNotFoundError(f"Workflow file not found: {path}")
        else:
            yaml_content = source
    else:
        yaml_content = str(source)

    data = yaml.safe_load(yaml_content)
    if not isinstance(data, dict):
        raise ValueError("Workflow YAML must be a mapping at the top level")

    return _parse_workflow_dict(data)


def _parse_workflow_dict(data: dict[str, Any]) -> WorkflowDAG:
    """Parse a validated workflow dictionary into a WorkflowDAG."""
    name = data.get("name", "unnamed-workflow")
    description = data.get("description", "")
    version = data.get("version", "1.0.0")
    global_variables = data.get("variables", {}) or {}

    nodes_raw = data.get("nodes", [])
    if not nodes_raw:
        raise ValueError("Workflow must have at least one node")

    nodes = [_parse_node_dict(n) for n in nodes_raw]

    return WorkflowDAG(
        name=name,
        description=description,
        version=version,
        nodes=nodes,
        variables=global_variables,
    )


def _parse_node_dict(data: dict[str, Any]) -> WorkflowNode:
    """Parse a single node dictionary into a WorkflowNode."""
    node_id = data.get("id")
    if not node_id:
        raise ValueError("Node must have an 'id' field")

    agent_type = data.get("agent_type", data.get("type", "general"))
    prompt_template = data.get("prompt", data.get("prompt_template", ""))
    if not prompt_template:
        raise ValueError(f"Node '{node_id}' must have a 'prompt' or 'prompt_template' field")

    # Parse tools (optional)
    tools = data.get("tools")
    if isinstance(tools, list):
        tools = [str(t) for t in tools]

    # Parse dependencies
    depends_on = data.get("depends_on", data.get("dependencies", []))
    if isinstance(depends_on, str):
        depends_on = [depends_on]
    depends_on = list(depends_on) if depends_on else []

    # Parse retry policy
    retry_raw = data.get("retry", data.get("retry_policy", {}))
    retry_policy = _parse_retry_policy(retry_raw)

    # Parse other options
    continue_on_failure = bool(data.get("continue_on_failure", False))
    variables = data.get("variables", {}) or {}
    timeout_seconds = data.get("timeout_seconds", data.get("timeout"))

    return WorkflowNode(
        id=node_id,
        agent_type=agent_type,
        prompt_template=prompt_template,
        tools=tools,
        depends_on=depends_on,
        retry_policy=retry_policy,
        continue_on_failure=continue_on_failure,
        variables=variables,
        timeout_seconds=int(timeout_seconds) if timeout_seconds else None,
    )


def _parse_retry_policy(raw: dict[str, Any] | int | None) -> RetryPolicy:
    """Parse retry policy from various formats."""
    if raw is None:
        return RetryPolicy()

    if isinstance(raw, int):
        # Simple integer = max_attempts
        return RetryPolicy(max_attempts=raw)

    if isinstance(raw, dict):
        return RetryPolicy(
            max_attempts=int(raw.get("max_attempts", raw.get("retries", 3))),
            backoff_multiplier=float(raw.get("backoff_multiplier", raw.get("multiplier", 2.0))),
            initial_delay_ms=int(raw.get("initial_delay_ms", raw.get("initial_delay", 1000))),
            max_delay_ms=int(raw.get("max_delay_ms", raw.get("max_delay", 30000))),
            retryable_exceptions=[
                str(e) for e in raw.get("retryable_exceptions", raw.get("exceptions", []))
            ],
        )

    return RetryPolicy()


def get_builtin_templates_dir() -> Path:
    """Return the path to built-in workflow templates."""
    return Path(__file__).parent / "templates"


def list_builtin_templates() -> list[str]:
    """List available built-in workflow template names."""
    templates_dir = get_builtin_templates_dir()
    if not templates_dir.exists():
        return []
    return [f.stem for f in templates_dir.glob("*.yaml")]


def load_builtin_template(name: str) -> WorkflowDAG:
    """
    Load a built-in workflow template by name.

    Args:
        name: Template name (without .yaml extension).

    Returns:
        Parsed WorkflowDAG.

    Raises:
        ValueError: If the template doesn't exist.
    """
    templates_dir = get_builtin_templates_dir()
    template_path = templates_dir / f"{name}.yaml"
    if not template_path.exists():
        available = list_builtin_templates()
        raise ValueError(
            f"Template '{name}' not found. Available templates: {available}"
        )
    return load_workflow(template_path)
