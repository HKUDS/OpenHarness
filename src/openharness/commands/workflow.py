"""CLI commands for workflow DAG orchestration."""

from __future__ import annotations

import json
import logging

import typer

log = logging.getLogger(__name__)

workflow_app = typer.Typer(
    name="workflow",
    help="Manage and execute workflow DAGs",
    add_completion=False,
)


@workflow_app.command("list")
def workflow_list() -> None:
    """List available workflow templates."""
    from openharness.workflow.parser import list_builtin_templates

    templates = list_builtin_templates()
    if not templates:
        print("No workflow templates found.")
        return

    print("Available workflow templates:")
    for name in templates:
        print(f"  - {name}")


@workflow_app.command("show")
def workflow_show(
    name: str = typer.Argument(..., help="Workflow template name"),
) -> None:
    """Show the definition of a workflow template."""
    from openharness.workflow.parser import load_builtin_template

    try:
        dag = load_builtin_template(name)
    except ValueError as exc:
        print(f"Error: {exc}")
        raise typer.Exit(1) from exc

    print(f"Name: {dag.name}")
    print(f"Description: {dag.description}")
    print(f"Version: {dag.version}")
    print(f"Nodes: {len(dag.nodes)}")
    print()

    order = dag.validate_execution_order()
    if order:
        print(f"Execution order: {' → '.join(order)}")
    else:
        print("Error: Workflow contains cycles")

    print()
    for node in dag.nodes:
        deps = f" (depends on: {', '.join(node.depends_on)})" if node.depends_on else ""
        print(f"  [{node.id}] {node.agent_type}{deps}")
        if node.retry_policy.max_attempts > 1:
            print(f"           retry: {node.retry_policy.max_attempts} attempts")


@workflow_app.command("run")
def workflow_run(
    name: str = typer.Argument(..., help="Workflow template name or path to YAML file"),
    variable: list[str] = typer.Option(
        None,
        "--var",
        "-v",
        help="Set workflow variable (KEY=VALUE, repeatable)",
    ),
    output_dir: str = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Directory for execution traces and reports",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate and show execution plan without running",
    ),
) -> None:
    """
    Execute a workflow DAG.

    NAME can be a built-in template name (e.g., 'refactor') or a path to a YAML file.
    """
    import asyncio
    from pathlib import Path as PathLib

    from openharness.workflow.engine import WorkflowEngine
    from openharness.workflow.parser import load_builtin_template, load_workflow
    from openharness.workflow.types import NodeStatus

    # Load workflow
    path = PathLib(name)
    if path.exists():
        dag = load_workflow(path)
    else:
        try:
            dag = load_builtin_template(name)
        except ValueError as exc:
            print(f"Error: {exc}")
            raise typer.Exit(1) from exc

    # Parse variables
    variables: dict[str, str] = {}
    for var in (variable or []):
        if "=" not in var:
            print(f"Error: Invalid variable format '{var}', expected KEY=VALUE")
            raise typer.Exit(1)
        key, value = var.split("=", 1)
        variables[key.strip()] = value.strip()

    # Dry run mode
    if dry_run:
        order = dag.validate_execution_order()
        if order is None:
            print("Error: Workflow contains cycles")
            raise typer.Exit(1)

        layers = dag.topological_layers()
        print(f"Workflow: {dag.name}")
        print(f"Description: {dag.description}")
        print(f"Nodes: {len(dag.nodes)}")
        print()
        print("Execution plan:")
        for i, layer in enumerate(layers):
            parallel = " [parallel]" if len(layer) > 1 else ""
            print(f"  Layer {i}:{parallel}")
            for node_id in layer:
                node = dag.node_map[node_id]
                print(f"    - {node_id} ({node.agent_type})")

        if variables:
            print()
            print("Variables:")
            for k, v in variables.items():
                print(f"  {k} = {v}")
        return

    # Execute workflow
    output_path = PathLib(output_dir) if output_dir else None

    async def _run() -> None:
        from openharness.config import load_settings
        from openharness.engine.query import QueryContext
        from openharness.api.client import AnthropicCompatibleClient
        from openharness.tools.base import ToolRegistry
        from openharness.permissions.checker import PermissionChecker
        from openharness.hooks import HookExecutor

        settings = load_settings()

        # Build query context (simplified for workflow execution)
        api_client = AnthropicCompatibleClient(
            api_key=settings.api_key or "",
            base_url=settings.base_url,
            model=settings.model,
        )
        tool_registry = ToolRegistry()
        permission_checker = PermissionChecker(settings)

        ctx = QueryContext(
            api_client=api_client,
            tool_registry=tool_registry,
            permission_checker=permission_checker,
            cwd=PathLib.cwd(),
            model=settings.model,
            system_prompt="",
            max_tokens=settings.max_tokens,
            hook_executor=HookExecutor(),
        )

        engine = WorkflowEngine(ctx, output_dir=output_path)
        results = await engine.execute(dag, variables=variables if variables else None)

        # Print summary
        print()
        print("=" * 60)
        print("Workflow Execution Summary")
        print("=" * 60)

        for node in dag.nodes:
            result = results.get(node.id)
            if result:
                status_icon = {
                    NodeStatus.COMPLETED: "✅",
                    NodeStatus.FAILED: "❌",
                    NodeStatus.SKIPPED: "⏭️",
                }.get(result.status, "❓")
                print(f"{status_icon} {node.id}: {result.status.value}")
                if result.error_message:
                    print(f"   Error: {result.error_message}")
                print(f"   Duration: {result.duration_seconds:.1f}s | Tokens: {result.input_tokens + result.output_tokens}")

        total_tokens = sum(r.input_tokens + r.output_tokens for r in results.values())
        total_duration = sum(r.duration_seconds for r in results.values())
        print()
        print(f"Total tokens: {total_tokens:,}")
        print(f"Total duration: {total_duration:.1f}s")

        # Check for failures
        failed = [nid for nid, r in results.items() if r.status == NodeStatus.FAILED]
        if failed:
            print(f"\n⚠️  Failed nodes: {', '.join(failed)}")
            raise typer.Exit(1)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        print("\n⚠️  Workflow execution interrupted")
        raise typer.Exit(130)
    except Exception as exc:
        print(f"\n❌ Workflow execution failed: {exc}")
        raise typer.Exit(1) from exc


@workflow_app.command("export")
def workflow_export(
    name: str = typer.Argument(..., help="Workflow template name or path to YAML file"),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Export format: json, dot, html",
    ),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (default: stdout for json)",
    ),
) -> None:
    """
    Export workflow DAG structure.

    Formats:
    - json: Machine-readable structure
    - dot: Graphviz DOT for visualization
    - html: Interactive HTML report
    """
    from pathlib import Path as PathLib

    from openharness.workflow.parser import load_builtin_template, load_workflow
    from openharness.workflow.trace import WorkflowTracer

    # Load workflow
    path = PathLib(name)
    if path.exists():
        dag = load_workflow(path)
    else:
        try:
            dag = load_builtin_template(name)
        except ValueError as exc:
            print(f"Error: {exc}")
            raise typer.Exit(1) from exc

    output_path = PathLib(output) if output else None

    if format == "json":
        data = {
            "name": dag.name,
            "description": dag.description,
            "version": dag.version,
            "variables": dag.variables,
            "execution_order": dag.validate_execution_order(),
            "nodes": [
                {
                    "id": n.id,
                    "agent_type": n.agent_type,
                    "depends_on": n.depends_on,
                    "tools": n.tools,
                    "retry_policy": n.retry_policy.dict(),
                    "continue_on_failure": n.continue_on_failure,
                    "timeout_seconds": n.timeout_seconds,
                }
                for n in dag.nodes
            ],
        }

        if output_path:
            output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(f"Exported to {output_path}")
        else:
            print(json.dumps(data, indent=2))

    elif format in ("dot", "html"):
        if output_path is None:
            print(f"Error: --output is required for {format} format")
            raise typer.Exit(1)

        tracer = WorkflowTracer(output_dir=output_path.parent)
        if format == "dot":
            path_result = tracer.export_graphviz(dag, results=None, output_path=output_path)
        else:
            # For HTML, we need mock results
            path_result = tracer.export_html_report(dag, results={}, output_path=output_path)
        print(f"Exported to {path_result}")

    else:
        print(f"Error: Unknown format '{format}'. Supported: json, dot, html")
        raise typer.Exit(1)
