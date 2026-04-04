# Changelog

All notable changes to OpenHarness should be recorded in this file.

The format is based on Keep a Changelog, and this project currently tracks changes in a lightweight, repository-oriented way.

## [Unreleased]

### Added

- `diagnose` skill: trace agent run failures and regressions using structured evidence from run artifacts.
- GitHub Actions CI workflow for Python linting, tests, and frontend TypeScript checks.
- `CONTRIBUTING.md` with local setup, validation commands, and PR expectations.
- `docs/SHOWCASE.md` with concrete OpenHarness usage patterns and demo commands.
- GitHub issue templates and a pull request template.

### Changed

- README now links to contribution docs, changelog, showcase material, and provider compatibility guidance.
- README quick start now includes a one-command demo and clearer provider compatibility notes.

## [0.1.0] - 2026-04-01

### Added

- Initial public release of OpenHarness.
- Core agent loop, tool registry, permission system, hooks, skills, plugins, MCP support, and terminal UI.
