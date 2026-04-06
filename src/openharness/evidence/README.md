# Run-Level Evidence Layer

The run-level evidence layer provides structured archiving for agent runs in OpenHarness. It captures comprehensive evidence of agent execution, including conversations, tasks, performance metrics, and errors.

## Overview

The evidence layer consists of several components:

- **Evidence Types**: Data models for different types of evidence records
- **Evidence Store**: Storage and retrieval system using JSON Lines format
- **Evidence Collector**: Collection utilities for capturing evidence during runs
- **Evidence Archiver**: Archiving, export, and reporting utilities
- **CLI Commands**: Command-line interface for managing evidence

## Evidence Types

The system captures the following types of evidence:

- `run_start` / `run_end`: Run lifecycle events
- `task_start` / `task_progress` / `task_end`: Task execution evidence
- `conversation_message`: Chat messages and tool calls
- `hook_execution`: Hook execution results
- `state_change`: Application state transitions
- `performance_metric`: Performance measurements
- `error`: Errors and exceptions

## Usage

### Basic Collection

```python
from openharness.evidence import EvidenceCollector

collector = EvidenceCollector(run_id="my-run-123")

# Record run start
collector.record_run_start(
    session_id="session-456",
    cwd="/workspace",
    command_line="oh --model gpt-4"
)

# Record task execution
collector.record_task_start(task_record)

# Record conversation
collector.record_conversation_message(message)

# Record run end
collector.record_run_end()
```

### Context Manager

```python
from openharness.evidence import EvidenceCollector

collector = EvidenceCollector()

async with collector.collect_run_evidence(
    session_id="session-456",
    cwd="/workspace"
) as collector:
    # Run your agent logic here
    # Evidence is automatically collected
    pass
```

### CLI Commands

```bash
# List all runs with evidence
oh evidence list

# Show summary of a run
oh evidence summary <run-id>

# Export evidence to JSON
oh evidence export <run-id> --format json

# Create compressed archive
oh evidence export <run-id> --format archive

# Generate human-readable report
oh evidence report <run-id>

# Clean up old evidence
oh evidence cleanup --days 30
```

## Storage Format

Evidence is stored in JSON Lines format under `~/.openharness/evidence/<run-id>/`:

```
evidence/
├── run-123/
│   ├── run_start.jsonl
│   ├── task_start.jsonl
│   ├── conversation_message.jsonl
│   └── run_end.jsonl
└── run-456/
    └── ...
```

Each line contains a complete evidence record:

```json
{
  "id": "uuid",
  "timestamp": 1234567890.123,
  "type": "run_start",
  "run_id": "run-123",
  "agent_id": "agent-1",
  "session_id": "session-456",
  "cwd": "/workspace",
  "command_line": "oh --model gpt-4"
}
```

## Integration Points

The evidence layer integrates with existing OpenHarness components:

- **Task Manager**: Automatically records task lifecycle events
- **Query Engine**: Captures conversation history and tool usage
- **Hook System**: Records hook execution results
- **Swarm Coordinator**: Tracks multi-agent interactions
- **Error Handling**: Captures exceptions and failures

## Configuration

Evidence collection can be configured through:

- Environment variables
- Configuration files
- Programmatic settings

The evidence directory location can be customized by setting the `EvidenceStore` base directory.

## Performance Considerations

- Evidence is written asynchronously to minimize impact on agent performance
- Large evidence collections can be archived and cleaned up automatically
- JSON Lines format allows for efficient streaming and partial reads
- Compression is used for long-term storage

## Security

Evidence may contain sensitive information such as:

- API keys (redacted in storage)
- File paths and contents
- Conversation history
- Error messages

Consider access controls and encryption for production deployments.