# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development commands

### Python / CLI
- Install dev dependencies: `uv sync --extra dev`
- Run the CLI: `uv run oh`
- Run the CLI with an active environment: `oh`
- Lint: `uv run ruff check src tests scripts`
- Run tests: `uv run pytest -q`
- Run a single test: `uv run pytest tests/path/to/test_file.py::test_name -q`
- Optional type check: `uv run mypy src/openharness`

### Frontend terminal UI
Run these from `frontend/terminal/`:
- Install dependencies: `npm ci`
- Start the Ink terminal UI: `npm start`
- Typecheck: `npx tsc --noEmit`

## Repository architecture
- `src/openharness/cli.py` is the Typer entrypoint and command surface for the Python CLI, including session flags and subcommands such as MCP, plugin, and auth.
- `src/openharness/engine/query.py` and `src/openharness/engine/query_engine.py` are the core agent loop. They stream model output, execute tool calls, apply permission checks, run hooks, and append tool results back into the conversation.
- `src/openharness/tools/` is the action surface exposed to the model.
- `src/openharness/permissions/` and `src/openharness/hooks/` are the governance rails around tool execution.
- `src/openharness/plugins/`, `src/openharness/skills/`, `src/openharness/mcp/`, `src/openharness/memory/`, and `src/openharness/services/` provide extensibility and runtime support.
- `frontend/terminal/` is a separate React + Ink terminal client; treat it as a separate app from the Python runtime.

## Where to look before changing behavior
- CLI and command wiring: `src/openharness/cli.py`
- Core runtime flow: `src/openharness/engine/query.py`, `src/openharness/engine/query_engine.py`
- Tool registration and execution: `src/openharness/tools/`
- Permission and approval behavior: `src/openharness/permissions/`
- Hook lifecycle: `src/openharness/hooks/`
- Plugin / skill / MCP integration: `src/openharness/plugins/`, `src/openharness/skills/`, `src/openharness/mcp/`
- Frontend terminal behavior: `frontend/terminal/`

## Repo-specific guidance
- Use `uv` for Python environment and dependency management. The repo requires Python 3.10+.
- Node.js 18+ is only needed when working on the frontend terminal UI.
- Before opening a PR, run the same core checks as CI: `uv run ruff check src tests scripts`, `uv run pytest -q`, and `cd frontend/terminal && npx tsc --noEmit` if frontend code changed.
- Keep PRs scoped and reviewable. When behavior changes, add or update tests.
- Update docs when CLI flags, workflows, or compatibility claims change.
- Add a short entry under `Unreleased` in `CHANGELOG.md` for user-visible changes.
- The PR template expects a concise summary of the problem and change, plus a validation section with the commands you ran.
