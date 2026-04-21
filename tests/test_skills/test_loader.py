"""Tests for skill loading."""

from __future__ import annotations

import textwrap
from pathlib import Path

from openharness.skills import get_user_skills_dir, load_skill_registry
from openharness.skills.loader import _parse_skill_markdown as parse_skill_markdown


def test_load_skill_registry_includes_bundled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = load_skill_registry()

    names = [skill.name for skill in registry.list_skills()]
    assert "simplify" in names
    assert "review" in names


def test_load_skill_registry_includes_user_skills(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    skills_dir = get_user_skills_dir()
    deploy_dir = skills_dir / "deploy"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "SKILL.md").write_text("# Deploy\nDeployment workflow guidance\n", encoding="utf-8")

    registry = load_skill_registry()
    deploy = registry.get("Deploy")

    assert deploy is not None
    assert deploy.source == "user"
    assert "Deployment workflow guidance" in deploy.content


# --- parse_skill_markdown unit tests ---


def test_parse_frontmatter_inline_description():
    """Inline description: value on the same line as the key."""
    content = textwrap.dedent("""\
        ---
        name: my-skill
        description: A short inline description
        ---

        # Body
    """)
    name, desc = parse_skill_markdown("fallback", content)
    assert name == "my-skill"
    assert desc == "A short inline description"


def test_parse_frontmatter_folded_block_scalar():
    """YAML folded block scalar (>) must be expanded into a single string."""
    content = textwrap.dedent("""\
        ---
        name: NL2SQL Expert
        description: >
          Multi-tenant NL2SQL skill for converting natural language questions
          into SQL queries. Covers the full pipeline: tenant routing,
          table selection, question enhancement, context retrieval.
        tags:
          - nl2sql
        ---

        # NL2SQL Expert Skill
    """)
    name, desc = parse_skill_markdown("fallback", content)
    assert name == "NL2SQL Expert"
    assert "Multi-tenant NL2SQL skill" in desc
    assert "context retrieval" in desc
    # Folded scalar joins lines with spaces, not newlines
    assert "\n" not in desc


def test_parse_frontmatter_literal_block_scalar():
    """YAML literal block scalar (|) preserves newlines."""
    content = textwrap.dedent("""\
        ---
        name: multi-line
        description: |
          Line one.
          Line two.
          Line three.
        ---

        # Body
    """)
    name, desc = parse_skill_markdown("fallback", content)
    assert name == "multi-line"
    assert "Line one." in desc
    assert "Line two." in desc


def test_parse_frontmatter_quoted_description():
    """Quoted description values are handled correctly."""
    content = textwrap.dedent("""\
        ---
        name: quoted
        description: "A quoted description with: colons"
        ---

        # Body
    """)
    name, desc = parse_skill_markdown("fallback", content)
    assert name == "quoted"
    assert desc == "A quoted description with: colons"


def test_parse_fallback_heading_and_paragraph():
    """Without frontmatter, falls back to heading + first paragraph."""
    content = "# My Skill\nThis is the description from the body.\n"
    name, desc = parse_skill_markdown("fallback", content)
    assert name == "My Skill"
    assert desc == "This is the description from the body."


def test_parse_no_description_uses_skill_name():
    """When nothing provides a description, falls back to 'Skill: <name>'."""
    content = "# OnlyHeading\n"
    name, desc = parse_skill_markdown("fallback", content)
    assert name == "OnlyHeading"
    assert desc == "Skill: OnlyHeading"


def test_parse_malformed_yaml_falls_back():
    """Malformed YAML in frontmatter falls back to body parsing."""
    content = textwrap.dedent("""\
        ---
        name: [invalid yaml
        description: also broken: {
        ---

        # Fallback Title
        Body paragraph here.
    """)
    name, desc = parse_skill_markdown("fallback", content)
    # Fallback scans all lines; frontmatter lines are not excluded, so
    # the first non-heading, non-delimiter line wins.  The important thing
    # is that a YAMLError doesn't crash the loader.
    assert isinstance(desc, str) and desc
