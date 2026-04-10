# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**OpenHarness** is an open-source Python agent harness — the infrastructure that wraps an LLM to make it a functional coding agent. It is compatible with Claude Code conventions and provides tool-use, skills, memory, and multi-agent coordination. The project is built with Hatchling and uses `uv` for package management.

CLI entry points: `oh` / `openharness` (agent harness), `ohmo` (personal-agent app with workspace/gateway/channels).

## Common Commands

```bash
# Install dev dependencies
uv sync --extra dev

# Run all tests
uv run pytest -q

# Run a single test file
uv run pytest tests/test_something.py -v

# Lint (ruff)
uv run ruff check src tests scripts

# Type check (mypy)
uv run mypy src/openharness

# Frontend TUI (React/Ink)
cd frontend/terminal && npm ci && npm start

# E2E tests
python scripts/test_harness_features.py
python scripts/e2e_smoke.py
```

## Architecture

### Source Layout

- `src/openharness/` — Core agent harness (Python)
- `ohmo/` — Personal-agent app (workspace, gateway, channels)
- `frontend/terminal/` — React/Ink TypeScript TUI
- `scripts/` — E2E and integration test scripts
- `tests/` — Unit/integration tests

### Core Modules (`src/openharness/`)

| Module | Purpose |
|--------|---------|
| `engine/` | Agent loop: query engine, streaming, retry logic |
| `tools/` | 43+ built-in tools (file I/O, shell, search, web, MCP) |
| `skills/` | Skill loading from `.md` files |
| `plugins/` | Plugin registry (compatible with anthropics/skills) |
| `memory/` | Persistent memory system |
| `coordinator/` | Multi-agent coordination |
| `permissions/` | Permission modes and path-based rules |
| `config/` | Settings, schema, migrations |
| `api/` | API clients (Anthropic, OpenAI, Codex, Copilot) |
| `channels/` | IM integrations (Telegram, Slack, Discord, Feishu) |
| `mcp/` | MCP client |
| `cli.py` | Main CLI entry point |

### CLI Structure

The CLI uses Typer. The main entry `openharness/cli.py` (~1000 lines) handles:
- Subcommands (agent, task, session, config, etc.)
- Output modes: `text`, `json`, `stream-json`
- Permission modes: `acceptEdits`, `bypassPermissions`, `dontAsk`, `plan`, `auto`

The `ohmo` personal-agent app lives in `ohmo/` with its own CLI and gateway/channel subsystems.

### Key Patterns

- **Tool registration**: Tools are registered via decorators in `tools/`. Each tool has a `@tool` decorator and schema definition.
- **Skill loading**: Skills are `.md` files loaded by `skills/` module. Compatible with Claude Code skill format.
- **Plugin system**: Plugins can provide tools, hooks, and agents. Loaded via `plugins/` registry.
- **Streaming**: Agent streaming uses SSE-style `stream-json` output mode for real-time tool call visibility.
- **Permissions**: Path-based rules in `permissions/` with allow/deny patterns, command denials, and permission modes.

## Development Notes

- Python >= 3.10 required; CI tests on 3.10 and 3.11
- Build system: Hatchling (`pyproject.toml`)
- Tests use `pytest-asyncio` with `asyncio_mode = "auto"`
- Frontend TUI is bundled into the wheel via `hatchling` force-include directives
- `ohmo` is bundled as a separate package within the same wheel
