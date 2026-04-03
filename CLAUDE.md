# CLAUDE.md

Project-level context for AI coding assistants working on OpenHarness.

## What is this project

OpenHarness (`oh`) is a lightweight, open-source Python reimplementation of Claude Code's agent harness architecture. It provides 43 tools, 54 commands, and full plugin/skill compatibility in ~11.7K lines of Python.

## Tech stack

- **Language**: Python 3.11+, TypeScript (frontend TUI)
- **Build**: hatchling, uv for dependency management
- **Core deps**: anthropic SDK, pydantic, typer, httpx, mcp, rich, textual
- **Frontend**: React 18 + Ink 5 (terminal UI), communicates via JSON protocol over stdin/stdout
- **Tests**: pytest + pytest-asyncio (async-first), pexpect for E2E

## Project layout

```
src/openharness/
  cli.py              # Entry point (typer). Commands: oh, openharness
  engine/             # Agent loop: run_query(), QueryEngine, messages, streaming
  api/                # Anthropic API client with retry + streaming
  tools/              # 43 tools, all extend BaseTool (Pydantic input validation)
  permissions/        # 3 modes: DEFAULT, PLAN, FULL_AUTO + path/command rules
  hooks/              # Lifecycle hooks: PRE/POST_TOOL_USE, hot-reload
  config/             # Settings (multi-layer: CLI > env > file > defaults)
  mcp/                # Model Context Protocol client
  skills/             # On-demand markdown knowledge (compatible with anthropics/skills)
  plugins/            # Plugin system (compatible with claude-code/plugins)
  coordinator/        # Multi-agent: subagent spawning, team coordination
  commands/           # 54 interactive slash commands
  prompts/            # System prompt assembly, CLAUDE.md injection
  memory/             # Persistent cross-session knowledge
  tasks/              # Background agent/shell tasks
  ui/                 # Backend host, React launcher, JSON protocol, Textual fallback
  services/           # Session storage, cron, LSP, compaction, OAuth
frontend/terminal/    # React + Ink TUI (TypeScript)
tests/                # Unit tests (mirrors src/ structure) + E2E in scripts/
```

## Common commands

```bash
# Install
uv sync --extra dev

# Run
uv run oh                          # Interactive TUI
uv run oh -p "prompt"              # Non-interactive (print mode)

# Tests
uv run pytest                      # All unit/integration tests
uv run pytest tests/test_engine    # Engine tests only
uv run pytest -x -q                # Stop on first failure, quiet

# Lint & type check
uv run ruff check src/
uv run mypy src/openharness/

# Frontend
cd frontend/terminal && npm install && npm run dev
```

## Architecture notes

- **Agent loop** (`engine/query.py`): User-driven request-response. Inner loop runs up to `max_turns=8` autonomous tool-call rounds per user message. Not a continuously running autonomous agent.
- **Tool execution pipeline**: Pre-hook -> permission check -> Pydantic validation -> execute -> post-hook. Errors return `ToolResultBlock(is_error=True)` rather than raising exceptions.
- **Streaming**: `run_query()` is an `AsyncIterator[StreamEvent]` — yields `AssistantTextDelta`, `ToolExecutionStarted/Completed`, `AssistantTurnComplete`.
- **API retry**: Exponential backoff with jitter, 3 retries, respects Retry-After header. Auth errors are never retried.
- **Concurrent tools**: Multiple tool calls in a single LLM turn execute via `asyncio.gather`.
- **Permission prompt**: In DEFAULT mode, mutating tools `await permission_prompt()` which blocks until user confirms in the TUI.

## Code conventions

- Async-first: all tool execution and API calls are async
- Pydantic v2 for all data models and tool input schemas
- Ruff for linting (line-length 100), mypy strict mode
- pytest with `asyncio_mode = "auto"`
- No docstrings required on obvious methods; keep code self-documenting
