from __future__ import annotations

from openharness.swarm.spawn_utils import build_inherited_env_vars


def test_build_inherited_env_vars_includes_openharness_auth_vars(monkeypatch):
    monkeypatch.setenv("OPENHARNESS_PROVIDER", "openai")
    monkeypatch.setenv("OPENHARNESS_BASE_URL", "https://relay.example.com/v1")
    monkeypatch.setenv("OPENHARNESS_OPENAI_API_KEY", "sk-oh-openai")
    monkeypatch.setenv("OPENHARNESS_ANTHROPIC_API_KEY", "sk-oh-anthropic")

    env = build_inherited_env_vars()

    assert env["OPENHARNESS_AGENT_TEAMS"] == "1"
    assert env["OPENHARNESS_PROVIDER"] == "openai"
    assert env["OPENHARNESS_BASE_URL"] == "https://relay.example.com/v1"
    assert env["OPENHARNESS_OPENAI_API_KEY"] == "sk-oh-openai"
    assert env["OPENHARNESS_ANTHROPIC_API_KEY"] == "sk-oh-anthropic"
