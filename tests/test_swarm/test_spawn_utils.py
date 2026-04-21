"""Tests for teammate spawn helper behavior."""

from __future__ import annotations

import sys

from openharness.swarm.spawn_utils import (
    TEAMMATE_COMMAND_ENV_VAR,
    build_inherited_cli_flags,
    build_inherited_env_vars,
    get_teammate_command,
)


def test_get_teammate_command_prefers_current_interpreter(monkeypatch):
    monkeypatch.delenv(TEAMMATE_COMMAND_ENV_VAR, raising=False)
    monkeypatch.setattr(sys, "executable", "/tmp/current-python")

    command = get_teammate_command()

    assert command == "/tmp/current-python"


def test_build_inherited_env_vars_disables_coordinator_mode(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_COORDINATOR_MODE", "1")

    env = build_inherited_env_vars()

    assert env["CLAUDE_CODE_COORDINATOR_MODE"] == "0"


# ---------------------------------------------------------------------------
# build_inherited_cli_flags – model handling
# ---------------------------------------------------------------------------


def test_build_inherited_cli_flags_explicit_model_included():
    flags = build_inherited_cli_flags(model="claude-opus-4-5")
    assert "--model" in flags
    idx = flags.index("--model")
    assert "claude-opus-4-5" in flags[idx + 1]


def test_build_inherited_cli_flags_inherit_model_excluded():
    """model='inherit' must NOT produce a --model flag so the subprocess
    picks up the parent's model from the OPENHARNESS_MODEL env var."""
    flags = build_inherited_cli_flags(model="inherit")
    assert "--model" not in flags


def test_build_inherited_cli_flags_none_model_excluded():
    flags = build_inherited_cli_flags(model=None)
    assert "--model" not in flags


def test_build_inherited_cli_flags_empty_string_model_excluded():
    flags = build_inherited_cli_flags(model="")
    assert "--model" not in flags


def test_build_inherited_cli_flags_forwards_system_prompt_as_replace():
    flags = build_inherited_cli_flags(system_prompt="You are a specialized worker.")

    assert "--system-prompt" in flags
    idx = flags.index("--system-prompt")
    assert "specialized worker" in flags[idx + 1]
    assert "--append-system-prompt" not in flags


def test_build_inherited_cli_flags_forwards_system_prompt_as_append():
    flags = build_inherited_cli_flags(
        system_prompt="Extra worker instructions.",
        system_prompt_mode="append",
    )

    assert "--append-system-prompt" in flags
    idx = flags.index("--append-system-prompt")
    assert "Extra worker instructions." in flags[idx + 1]
    assert "--system-prompt" not in flags
