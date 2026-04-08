# Workflow DAG Engine

The Workflow DAG Engine adds **multi-agent orchestration** to OpenHarness. Instead of a single agent loop, you can now define complex workflows with dependency-aware, parallel-capable, auto-retrying node execution.

## Overview

```
User Request: "Refactor this module, write tests, and update docs"

Workflow DAG:

  [Code Analysis] ──→ [Refactor Implementation] ──→ [Code Review]
                          │                              │
                          ▼                              ▼
                     [Unit Tests] ──→ [Run Tests] ──→ [Documentation]
                          │
                          ▼
                    (Failed?) ──→ [Auto Debug & Fix] ──→ Re-run Tests
```

Each node runs through the full Agent Loop with its own prompt, tool set, and retry policy. Nodes execute in parallel when their dependencies are satisfied.

## Quick Start

### List Available Templates

```bash
oh workflow list
```

### Show a Template

```bash
oh workflow show refactor
```

### Run a Workflow

```bash
oh workflow run refactor -v target_path=src/openharness/tools
```

### Dry Run (Preview Execution Plan)

```bash
oh workflow run refactor -v target_path=src/my_module --dry-run
```

### Export Workflow Structure

```bash
# JSON structure
oh workflow export refactor -f json

# Graphviz DOT for visualization
oh workflow export refactor -f dot -o workflow.dot

# Interactive HTML report
oh workflow export refactor -f html -o report.html
```

## Built-in Templates

### `refactor` — Code Refactoring Workflow

```
Code Analysis → Refactor Implementation → Code Review
```

Analyzes code for complexity and smells, implements refactoring, then verifies correctness.

```bash
oh workflow run refactor \
  -v target_path=src/my_module \
  -v refactoring_goal="Reduce cyclomatic complexity below 10"
```

### `feature-dev` — Feature Development Workflow

```
Planning → Implementation → Unit Tests → Run Tests → Documentation
```

End-to-end feature development with planning, coding, testing, and documentation.

```bash
oh workflow run feature-dev \
  -v feature_description="Add user authentication with JWT tokens" \
  -v target_module=src/auth
```

### `test-and-docs` — Test Fix and Documentation Update

```
Run Tests → Fix Failures → Verify Fixes → Update Documentation
```

Runs tests, automatically fixes failures, then updates relevant documentation.

```bash
oh workflow run test-and-docs \
  -v test_command="pytest tests/unit" \
  -v docs_path=docs/
```

## Defining Custom Workflows

Create a YAML file describing your workflow:

```yaml
name: my-workflow
description: "Custom workflow example"
version: "1.0.0"

variables:
  target: ""

nodes:
  - id: analyze
    agent_type: reviewer
    prompt: |
      Analyze the code at ${target} and provide recommendations.
    retry:
      max_attempts: 2
      backoff_multiplier: 2.0
    timeout_seconds: 120

  - id: implement
    agent_type: coder
    depends_on:
      - analyze
    prompt: |
      Implement improvements based on:
      ${analyze_output}
    tools:
      - read_file
      - write_file
      - edit
    retry:
      max_attempts: 3
    continue_on_failure: false

  - id: test
    agent_type: tester
    depends_on:
      - implement
    prompt: |
      Run tests and verify the changes work correctly.
    tools:
      - bash
      - read_file
```

Run your custom workflow:

```bash
oh workflow run my-workflow.yaml -v target=src/main.py
```

## Workflow Schema Reference

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Workflow name (display and logging) |
| `description` | string | No | Human-readable description |
| `version` | string | No | Semantic version (default: "1.0.0") |
| `variables` | dict | No | Global variables for all nodes |
| `nodes` | list | Yes | List of workflow nodes |

### Node Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique identifier (lowercase, starts with letter) |
| `agent_type` | string | No | Agent specialization: `general`, `coder`, `reviewer`, `tester`, `writer`, `debugger` |
| `prompt` | string | Yes | Prompt template with `${variable}` interpolation |
| `tools` | list | No | Tool whitelist (None = use engine defaults) |
| `depends_on` | list | No | Upstream node IDs that must complete first |
| `retry` | int or dict | No | Retry policy (see below) |
| `continue_on_failure` | bool | No | If true, downstream nodes run even if this fails |
| `variables` | dict | No | Node-specific variables |
| `timeout_seconds` | int | No | Node execution timeout (minimum 10s) |

### Retry Policy

Simple form (max attempts only):

```yaml
retry: 5
```

Full configuration:

```yaml
retry:
  max_attempts: 3
  backoff_multiplier: 2.0
  initial_delay_ms: 1000
  max_delay_ms: 30000
  retryable_exceptions:
    - TimeoutError
    - ConnectionError
```

## Variable Interpolation

Variables are interpolated in prompt templates using `${variable_name}` syntax:

```yaml
variables:
  module: auth
  path: src/auth/

nodes:
  - id: review
    prompt: |
      Review the ${module} module at ${path}
```

### Automatic Variables from Upstream Results

When a node depends on another, the upstream node's results are automatically available:

- `${<node_id>_output}` — The output text from the upstream node
- `${<node_id>_status}` — The status (completed/failed/skipped) of the upstream node

```yaml
nodes:
  - id: analyze
    prompt: "Analyze code and provide recommendations"

  - id: fix
    depends_on:
      - analyze
    prompt: |
      Address the issues identified:
      ${analyze_output}
```

## Parallel Execution

Nodes without interdependencies execute in parallel:

```yaml
nodes:
  - id: root
    prompt: "Initial analysis"

  - id: left
    depends_on: [root]
    prompt: "Work on aspect A"

  - id: right
    depends_on: [root]
    prompt: "Work on aspect B"

  - id: merge
    depends_on: [left, right]
    prompt: |
      Combine results:
      Left: ${left_output}
      Right: ${right_output}
```

Execution order:
1. Layer 0: `root` (sequential)
2. Layer 1: `left`, `right` (parallel)
3. Layer 2: `merge` (sequential, waits for both)

## Failure Handling

### Retry with Backoff

Nodes automatically retry on failure with exponential backoff:

```yaml
nodes:
  - id: fragile-operation
    prompt: "Call external API"
    retry:
      max_attempts: 3
      initial_delay_ms: 2000    # 2s
      backoff_multiplier: 2.0   # 2s → 4s → 8s
```

### Continue on Failure

Allow downstream nodes to run even if a node fails:

```yaml
nodes:
  - id: optional-step
    prompt: "Optional analysis"
    continue_on_failure: true

  - id: main-flow
    depends_on: [optional-step]
    prompt: "Continue regardless of optional-step outcome"
```

### Timeout

Nodes can have execution timeouts:

```yaml
nodes:
  - id: long-running
    prompt: "This might take a while"
    timeout_seconds: 600  # 10 minutes
```

## Observability

### Execution Traces

Workflows automatically export execution traces:

```bash
oh workflow run refactor -v target_path=src/main \
  --output-dir ./traces/
```

This generates:
- JSON trace with full execution details
- Execution summary with token usage and timing

### Programmatic Usage

```python
import asyncio
from openharness.workflow.engine import WorkflowEngine
from openharness.workflow.parser import load_workflow
from openharness.engine.query import QueryContext

async def run_workflow():
    dag = load_workflow("my-workflow.yaml")
    engine = WorkflowEngine(query_context, output_dir=Path("./traces"))
    results = await engine.execute(dag, variables={"target": "src/main.py"})

    for node_id, result in results.items():
        print(f"{node_id}: {result.status}")
        print(f"  Tokens: {result.input_tokens + result.output_tokens}")
        print(f"  Duration: {result.duration_seconds:.1f}s")

asyncio.run(run_workflow())
```

## Architecture

### Components

| Module | Responsibility |
|--------|---------------|
| `types.py` | Pydantic data models: `WorkflowNode`, `WorkflowDAG`, `NodeResult`, `RetryPolicy` |
| `scheduler.py` | DAG scheduling: topological sort, layered parallel execution |
| `executor.py` | Node execution: prompt rendering, Agent Loop integration, tool restriction |
| `engine.py` | High-level engine: unified API, retry logic, trace export |
| `parser.py` | YAML parsing: file loading, template discovery, validation |
| `recovery.py` | Failure recovery: retry decisions, compensation actions |
| `trace.py` | Observability: JSON/DOT/HTML export, execution visualization |

### Execution Flow

```
User Request
    │
    ▼
WorkflowEngine.execute(dag)
    │
    ├── Validate DAG structure (cycle detection)
    │
    ├── Topological sort → parallel layers
    │
    └── For each layer (in order):
            │
            ├── Execute all nodes concurrently
            │   │
            │   ├── Render prompt with variables
            │   ├── Build restricted tool context (if tools specified)
            │   ├── Run Agent Loop (run_query)
            │   └── Retry on failure (with backoff)
            │
            └── Collect results → pass to next layer as variables
```

## Extending

### Adding Custom Templates

Add YAML files to `src/openharness/workflow/templates/` and they'll appear in `oh workflow list`.

### Custom Agent Types

The `agent_type` field is informational and can be used by future integrations to select specialized prompts or tool configurations. Currently all agent types use the same Agent Loop.

### Integration with External Systems

The JSON trace export can be consumed by:
- Monitoring dashboards (Grafana, DataDog)
- Workflow analytics pipelines
- CI/CD systems for automated code review

## Troubleshooting

### "Cycle detected in workflow DAG"

Your workflow has a circular dependency. Check `depends_on` fields:

```yaml
# Bad: A → B → A
nodes:
  - id: a
    depends_on: [b]
  - id: b
    depends_on: [a]

# Good: A → B → C
nodes:
  - id: a
    prompt: "First"
  - id: b
    depends_on: [a]
    prompt: "Second"
```

### "Tool not found in registry"

The tool name in your workflow doesn't match registered tools. Check available tools:

```python
from openharness.tools.base import ToolRegistry
print(ToolRegistry()._tools.keys())
```

### Variable Interpolation Not Working

Ensure variables are defined at the correct scope:
- Global `variables:` at top level → available to all nodes
- Node-level `variables:` → only available to that node
- Upstream results → `${<node_id>_output}` automatically available to downstream nodes
