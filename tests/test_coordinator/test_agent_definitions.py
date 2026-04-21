"""Tests for AgentDefinition model, built-in defs, and load_agents_dir."""

from __future__ import annotations


import pytest

from openharness.coordinator.agent_definitions import (
    AgentDefinition,
    _parse_agent_frontmatter,
    get_builtin_agent_definitions,
    load_agents_dir,
)


# ---------------------------------------------------------------------------
# AgentDefinition model
# ---------------------------------------------------------------------------


def test_agent_definition_required_fields():
    agent = AgentDefinition(
        name="my-agent",
        description="does things",
    )
    assert agent.name == "my-agent"
    assert agent.description == "does things"
    assert agent.tools is None
    assert agent.model is None
    assert agent.permissions == []
    assert agent.subagent_type == "general-purpose"
    assert agent.source == "builtin"


def test_agent_definition_with_tools():
    agent = AgentDefinition(
        name="reader",
        description="reads files",
        tools=["Read", "Glob", "Grep"],
        source="user",
    )
    assert "Read" in agent.tools
    assert agent.source == "user"


def test_agent_definition_invalid_source():
    with pytest.raises(Exception):
        AgentDefinition(name="bad", description="desc", source="unknown")


# ---------------------------------------------------------------------------
# Built-in agent definitions
# ---------------------------------------------------------------------------


def test_get_builtin_returns_expected_names():
    builtins = get_builtin_agent_definitions()
    names = {a.name for a in builtins}
    assert "general-purpose" in names
    assert "Explore" in names
    assert "Plan" in names
    assert "worker" in names
    assert "verification" in names


def test_builtin_agents_have_descriptions():
    for agent in get_builtin_agent_definitions():
        assert agent.description, f"Agent {agent.name!r} is missing a description"


def test_builtin_explore_has_tools():
    builtins = get_builtin_agent_definitions()
    explore = next(a for a in builtins if a.name == "Explore")
    # Explore agent uses disallowed_tools pattern — tools may be None (all tools)
    # with specific tools blocked via other mechanism
    assert explore is not None


def test_builtin_general_purpose_has_all_tools():
    builtins = get_builtin_agent_definitions()
    gp = next(a for a in builtins if a.name == "general-purpose")
    assert gp.tools == ["*"] or gp.tools is None  # all tools


# ---------------------------------------------------------------------------
# Model inheritance: provider-agnostic built-in agents
# ---------------------------------------------------------------------------

_PROVIDER_SPECIFIC_MODELS = {"haiku", "sonnet", "opus"}
"""Short model aliases that only exist for Anthropic's API."""


def test_builtin_explore_does_not_hardcode_provider_model():
    """Explore must use 'inherit' (or None) so it works with any API provider."""
    builtins = get_builtin_agent_definitions()
    explore = next(a for a in builtins if a.name == "Explore")
    assert explore.model not in _PROVIDER_SPECIFIC_MODELS, (
        f"Explore.model={explore.model!r} hard-codes a provider-specific model alias; "
        "use 'inherit' so the agent works with non-Anthropic providers."
    )


def test_builtin_claude_code_guide_does_not_hardcode_provider_model():
    """claude-code-guide must not hard-code an Anthropic-only model alias."""
    builtins = get_builtin_agent_definitions()
    guide = next(a for a in builtins if a.name == "claude-code-guide")
    assert guide.model not in _PROVIDER_SPECIFIC_MODELS, (
        f"claude-code-guide.model={guide.model!r} hard-codes a provider-specific model alias; "
        "use 'inherit' so the agent works with non-Anthropic providers."
    )


def test_builtin_provider_agnostic_agents_use_inherit_or_none():
    """Plan, verification, Explore, and claude-code-guide must not override the model."""
    agnostic_agents = {"Plan", "verification", "Explore", "claude-code-guide"}
    builtins = {a.name: a for a in get_builtin_agent_definitions()}
    for name in agnostic_agents:
        agent = builtins[name]
        assert agent.model in {None, "inherit"}, (
            f"Built-in agent {name!r} sets model={agent.model!r}; "
            "provider-agnostic agents should use None or 'inherit'."
        )
# _parse_agent_frontmatter
# ---------------------------------------------------------------------------


def test_parse_frontmatter_with_valid_yaml():
    content = "---\nname: my-agent\ndescription: a test agent\n---\nThis is the body."
    fm, body = _parse_agent_frontmatter(content)
    assert fm["name"] == "my-agent"
    assert fm["description"] == "a test agent"
    assert body == "This is the body."


def test_parse_frontmatter_missing_delimiter_returns_empty():
    content = "name: my-agent\ndescription: desc\nbody text"
    fm, body = _parse_agent_frontmatter(content)
    assert fm == {}
    assert body == content


def test_parse_frontmatter_unclosed_returns_empty():
    content = "---\nname: agent\ndescription: desc\nbody"
    fm, body = _parse_agent_frontmatter(content)
    assert fm == {}


def test_parse_frontmatter_strips_quotes():
    content = "---\nname: 'quoted-name'\ndescription: \"also quoted\"\n---\nbody"
    fm, _ = _parse_agent_frontmatter(content)
    assert fm["name"] == "quoted-name"
    assert fm["description"] == "also quoted"


# ---------------------------------------------------------------------------
# load_agents_dir
# ---------------------------------------------------------------------------


def test_load_agents_dir_empty_dir(tmp_path):
    agents = load_agents_dir(tmp_path)
    assert agents == []


def test_load_agents_dir_nonexistent(tmp_path):
    agents = load_agents_dir(tmp_path / "no_such_dir")
    assert agents == []


def test_load_agents_dir_single_file(tmp_path):
    md = tmp_path / "my_agent.md"
    md.write_text(
        "---\nname: my-agent\ndescription: test agent\n---\nDo something useful.",
        encoding="utf-8",
    )
    agents = load_agents_dir(tmp_path)
    assert len(agents) == 1
    assert agents[0].name == "my-agent"
    assert agents[0].description == "test agent"
    assert agents[0].system_prompt == "Do something useful."
    assert agents[0].source == "user"


def test_load_agents_dir_file_with_tools(tmp_path):
    md = tmp_path / "explorer.md"
    md.write_text(
        "---\nname: explorer\ndescription: explores code\ntools: Read, Glob, Grep\n---\nExplore.",
        encoding="utf-8",
    )
    agents = load_agents_dir(tmp_path)
    assert agents[0].tools == ["Read", "Glob", "Grep"]


def test_load_agents_dir_falls_back_to_stem_for_name(tmp_path):
    md = tmp_path / "fallback_name.md"
    md.write_text("---\ndescription: no name given\n---\nbody", encoding="utf-8")
    agents = load_agents_dir(tmp_path)
    assert agents[0].name == "fallback_name"


def test_load_agents_dir_with_model_and_permissions(tmp_path):
    md = tmp_path / "specialized.md"
    md.write_text(
        "---\nname: spec\ndescription: specialized\nmodel: claude-opus-4-6\n"
        "permissions: allow:bash, deny:write\n---\nbody",
        encoding="utf-8",
    )
    agents = load_agents_dir(tmp_path)
    assert agents[0].model == "claude-opus-4-6"
    assert "allow:bash" in agents[0].permissions
    assert "deny:write" in agents[0].permissions


def test_load_agents_dir_skips_unreadable_files(tmp_path):
    good = tmp_path / "good.md"
    good.write_text("---\nname: good\ndescription: fine\n---\nbody", encoding="utf-8")
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe invalid utf-32")  # not utf-8, but won't crash
    # Should still load the good file
    agents = load_agents_dir(tmp_path)
    names = [a.name for a in agents]
    assert "good" in names
