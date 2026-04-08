"""Execution tracing and observability for workflow DAGs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openharness.workflow.types import NodeResult, NodeStatus, WorkflowDAG

log = logging.getLogger(__name__)


class WorkflowTracer:
    """
    Exports workflow execution traces to JSON and Graphviz DOT format.

    Provides observability into workflow execution for debugging,
    auditing, and visualization.
    """

    def __init__(self, output_dir: Path | None = None) -> None:
        """
        Initialize the tracer.

        Args:
            output_dir: Directory for trace exports. None = no export.
        """
        self._output_dir = output_dir
        self.last_export_path: Path | None = None

    def export_json(
        self,
        dag: WorkflowDAG,
        results: dict[str, NodeResult],
        output_path: Path | None = None,
    ) -> Path:
        """
        Export execution trace as JSON.

        Args:
            dag: The executed workflow DAG.
            results: Node execution results keyed by node ID.
            output_path: Custom output path. Auto-generated if None.

        Returns:
            Path to the exported JSON file.
        """
        if self._output_dir is None and output_path is None:
            raise ValueError("No output directory configured for trace export")

        if output_path is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            safe_name = dag.name.replace(" ", "-").lower()
            output_path = self._output_dir / f"{safe_name}-{timestamp}.json"

        if self._output_dir is not None:
            self._output_dir.mkdir(parents=True, exist_ok=True)

        trace_data = self._build_trace_dict(dag, results)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(trace_data, f, indent=2, ensure_ascii=False, default=str)

        self.last_export_path = output_path
        log.info("JSON trace exported to %s", output_path)
        return output_path

    def export_graphviz(
        self,
        dag: WorkflowDAG,
        results: dict[str, NodeResult] | None = None,
        output_path: Path | None = None,
    ) -> Path:
        """
        Export workflow DAG as Graphviz DOT file.

        Args:
            dag: The workflow DAG to visualize.
            results: Optional execution results for coloring nodes.
            output_path: Custom output path. Auto-generated if None.

        Returns:
            Path to the exported DOT file.
        """
        if self._output_dir is None and output_path is None:
            raise ValueError("No output directory configured for trace export")

        if output_path is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            safe_name = dag.name.replace(" ", "-").lower()
            output_path = self._output_dir / f"{safe_name}-{timestamp}.dot"

        if self._output_dir is not None:
            self._output_dir.mkdir(parents=True, exist_ok=True)

        dot_content = self._build_graphviz(dag, results)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(dot_content)

        self.last_export_path = output_path
        log.info("Graphviz DOT exported to %s", output_path)
        return output_path

    def _build_trace_dict(
        self,
        dag: WorkflowDAG,
        results: dict[str, NodeResult],
    ) -> dict[str, Any]:
        """Build a dictionary representation of the execution trace."""
        return {
            "workflow": {
                "name": dag.name,
                "description": dag.description,
                "version": dag.version,
                "num_nodes": len(dag.nodes),
            },
            "execution": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_nodes": len(results),
                "completed": sum(
                    1 for r in results.values() if r.status == NodeStatus.COMPLETED
                ),
                "failed": sum(
                    1 for r in results.values() if r.status == NodeStatus.FAILED
                ),
                "skipped": sum(
                    1 for r in results.values() if r.status == NodeStatus.SKIPPED
                ),
                "total_tokens": sum(
                    r.input_tokens + r.output_tokens for r in results.values()
                ),
                "total_duration_seconds": round(
                    sum(r.duration_seconds for r in results.values()), 2
                ),
            },
            "nodes": {
                nid: {
                    "status": r.status.value,
                    "output": r.output[:500] if r.output else "",  # Truncate long outputs
                    "error_message": r.error_message,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "duration_seconds": round(r.duration_seconds, 2),
                    "attempts": r.attempts,
                    "metadata": r.metadata,
                }
                for nid, r in results.items()
            },
            "dag_structure": {
                "execution_order": dag.validate_execution_order(),
                "layers": dag.topological_layers() if dag.validate_execution_order() else None,
                "adjacency": dict(dag.adjacency),
            },
        }

    def _build_graphviz(
        self,
        dag: WorkflowDAG,
        results: dict[str, NodeResult] | None,
    ) -> str:
        """Build Graphviz DOT representation of the workflow DAG."""
        lines = [
            "digraph Workflow {",
            '  rankdir=LR;',
            '  node [shape=box, style=filled, fontname="Helvetica"];',
            f'  label="{dag.name}\\n{dag.description}";',
            '  fontsize=16;',
            "",
        ]

        # Color mapping for node statuses
        status_colors = {
            NodeStatus.COMPLETED: "#4ade80",  # Green
            NodeStatus.FAILED: "#f87171",      # Red
            NodeStatus.SKIPPED: "#fbbf24",     # Yellow
            NodeStatus.RUNNING: "#60a5fa",     # Blue
            NodeStatus.PENDING: "#e5e7eb",     # Gray
            NodeStatus.RETRYING: "#c084fc",    # Purple
        }

        # Add nodes
        for node in dag.nodes:
            fill_color = "#e5e7eb"  # Default gray
            label = node.id
            tooltip = ""

            if results and node.id in results:
                r = results[node.id]
                fill_color = status_colors.get(r.status, "#e5e7eb")
                tooltip = f"Status: {r.status.value}"
                if r.error_message:
                    tooltip += f"\\nError: {r.error_message[:100]}"
                if r.duration_seconds > 0:
                    tooltip += f"\\nDuration: {r.duration_seconds:.1f}s"
            else:
                fill_color = "#e5e7eb"

            # Escape special characters for DOT
            safe_label = label.replace('"', '\\"')
            safe_tooltip = tooltip.replace('"', '\\"')

            lines.append(
                f'  "{safe_label}" [fillcolor="{fill_color}", '
                f'label="{safe_label}", '
                f'tooltip="{safe_tooltip}"];'
            )

        lines.append("")

        # Add edges
        for node in dag.nodes:
            for dep_id in node.depends_on:
                safe_dep = dep_id.replace('"', '\\"')
                safe_node = node.id.replace('"', '\\"')
                lines.append(f'  "{safe_dep}" -> "{safe_node}";')

        lines.append("}")
        return "\n".join(lines)

    def export_html_report(
        self,
        dag: WorkflowDAG,
        results: dict[str, NodeResult],
        output_path: Path | None = None,
    ) -> Path:
        """
        Export an HTML report with interactive visualization.

        Args:
            dag: The executed workflow DAG.
            results: Node execution results.
            output_path: Custom output path. Auto-generated if None.

        Returns:
            Path to the exported HTML file.
        """
        if self._output_dir is None and output_path is None:
            raise ValueError("No output directory configured for trace export")

        if output_path is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            safe_name = dag.name.replace(" ", "-").lower()
            output_path = self._output_dir / f"{safe_name}-{timestamp}.html"

        if self._output_dir is not None:
            self._output_dir.mkdir(parents=True, exist_ok=True)

        html = self._build_html_report(dag, results)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        self.last_export_path = output_path
        log.info("HTML report exported to %s", output_path)
        return output_path

    def _build_html_report(
        self,
        dag: WorkflowDAG,
        results: dict[str, NodeResult],
    ) -> str:
        """Build a self-contained HTML report."""
        total_tokens = sum(r.input_tokens + r.output_tokens for r in results.values())
        total_duration = sum(r.duration_seconds for r in results.values())
        completed = sum(1 for r in results.values() if r.status == NodeStatus.COMPLETED)
        failed = sum(1 for r in results.values() if r.status == NodeStatus.FAILED)

        # Build node table rows
        node_rows = ""
        for node in dag.nodes:
            r = results.get(node.id)
            if r:
                status_color = {
                    NodeStatus.COMPLETED: "green",
                    NodeStatus.FAILED: "red",
                    NodeStatus.SKIPPED: "orange",
                }.get(r.status, "gray")
                status_text = r.status.value
                duration = f"{r.duration_seconds:.2f}s"
                error = r.error_message or "-"
                output_preview = (r.output[:100] + "...") if r.output and len(r.output) > 100 else (r.output or "-")
            else:
                status_color = "gray"
                status_text = "not executed"
                duration = "-"
                error = "-"
                output_preview = "-"

            node_rows += f"""
            <tr>
                <td><strong>{node.id}</strong></td>
                <td><span style="color: {status_color}; font-weight: bold;">{status_text}</span></td>
                <td>{duration}</td>
                <td>{r.input_tokens + r.output_tokens if r else 0}</td>
                <td>{r.attempts if r else 0}</td>
                <td style="color: red;">{error}</td>
                <td><pre style="max-width: 300px; overflow: hidden; text-overflow: ellipsis;">{output_preview}</pre></td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Workflow Report: {dag.name}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1 {{ color: #333; border-bottom: 2px solid #0066cc; padding-bottom: 10px; }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .summary-card {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .summary-card .value {{ font-size: 2em; font-weight: bold; color: #0066cc; }}
        .summary-card .label {{ color: #666; font-size: 0.9em; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-radius: 8px;
            overflow: hidden;
        }}
        th {{ background: #0066cc; color: white; padding: 12px; text-align: left; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #eee; }}
        tr:hover {{ background: #f8f9fa; }}
        .timestamp {{ color: #888; font-size: 0.9em; }}
    </style>
</head>
<body>
    <h1>🔄 Workflow Report: {dag.name}</h1>
    <p class="timestamp">Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
    <p><strong>Description:</strong> {dag.description or 'N/A'}</p>
    <p><strong>Version:</strong> {dag.version}</p>

    <div class="summary">
        <div class="summary-card">
            <div class="value">{len(dag.nodes)}</div>
            <div class="label">Total Nodes</div>
        </div>
        <div class="summary-card">
            <div class="value" style="color: green;">{completed}</div>
            <div class="label">Completed</div>
        </div>
        <div class="summary-card">
            <div class="value" style="color: red;">{failed}</div>
            <div class="label">Failed</div>
        </div>
        <div class="summary-card">
            <div class="value">{total_tokens:,}</div>
            <div class="label">Total Tokens</div>
        </div>
        <div class="summary-card">
            <div class="value">{total_duration:.1f}s</div>
            <div class="label">Duration</div>
        </div>
    </div>

    <h2>Node Execution Details</h2>
    <table>
        <thead>
            <tr>
                <th>Node ID</th>
                <th>Status</th>
                <th>Duration</th>
                <th>Tokens</th>
                <th>Attempts</th>
                <th>Error</th>
                <th>Output Preview</th>
            </tr>
        </thead>
        <tbody>
            {node_rows}
        </tbody>
    </table>
</body>
</html>"""

        return html
