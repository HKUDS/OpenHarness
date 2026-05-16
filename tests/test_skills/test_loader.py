"""Tests for skill loading."""

from __future__ import annotations

import textwrap
from pathlib import Path

from openharness.config.settings import Settings
from openharness.skills import get_user_skills_dir, load_skill_registry
from openharness.skills.loader import discover_project_skill_dirs, get_user_skill_dirs
from openharness.skills.bundled import _parse_frontmatter as parse_bundled_frontmatter
from openharness.skills.loader import _parse_skill_markdown as parse_skill_markdown


def test_load_skill_registry_includes_bundled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = load_skill_registry()

    names = [skill.name for skill in registry.list_skills()]
    assert "simplify" in names
    assert "review" in names
    assert "skill-creator" in names

    skill_creator = registry.get("skill-creator")
    assert skill_creator is not None
    assert skill_creator.source == "bundled"
    assert "Create, improve, and verify OpenHarness skills" in skill_creator.description


def _write_skill(root: Path, name: str, body: str | None = None) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(body or f"# {name}\n{name} guidance\n", encoding="utf-8")
    return skill_file


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


def test_load_skill_registry_includes_user_compat_skill_dirs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    claude_skill = _write_skill(tmp_path / "home" / ".claude" / "skills", "claude-review")
    agents_skill = _write_skill(tmp_path / "home" / ".agents" / "skills", "agents-plan")

    registry = load_skill_registry()

    assert registry.get("claude-review") is not None
    assert registry.get("agents-plan") is not None
    assert registry.get("claude-review").source == "user"  # type: ignore[union-attr]
    assert registry.get("agents-plan").source == "user"  # type: ignore[union-attr]
    assert str(claude_skill) in (registry.get("claude-review").path or "")  # type: ignore[union-attr]
    assert str(agents_skill) in (registry.get("agents-plan").path or "")  # type: ignore[union-attr]


def test_get_user_skill_dirs_includes_openharness_claude_and_agents(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    dirs = get_user_skill_dirs()

    assert tmp_path / "config" / "skills" in dirs
    assert tmp_path / "home" / ".claude" / "skills" in dirs
    assert tmp_path / "home" / ".agents" / "skills" in dirs


def test_user_skill_metadata_tracks_command_name_and_frontmatter_flags(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    skills_dir = get_user_skills_dir()
    deploy_dir = skills_dir / "deploy-flow"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "SKILL.md").write_text(
        textwrap.dedent("""\
            ---
            name: Deploy Flow
            description: Release deployment workflow.
            user-invocable: false
            disable-model-invocation: true
            model: gpt-5.4
            argument-hint: ENV
            ---

            # Deploy Flow
            """),
        encoding="utf-8",
    )

    registry = load_skill_registry()
    by_command = registry.get("deploy-flow")
    by_display = registry.get("Deploy Flow")

    assert by_command is not None
    assert by_display is by_command
    assert by_command.name == "Deploy Flow"
    assert by_command.command_name == "deploy-flow"
    assert by_command.display_name == "Deploy Flow"
    assert by_command.user_invocable is False
    assert by_command.disable_model_invocation is True
    assert by_command.model == "gpt-5.4"
    assert by_command.argument_hint == "ENV"


def test_project_skills_load_by_default_from_supported_dirs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    _write_skill(repo / ".openharness" / "skills", "oh-project")
    _write_skill(repo / ".agents" / "skills", "agents-project")
    _write_skill(repo / ".claude" / "skills", "claude-project")

    registry = load_skill_registry(repo, settings=Settings())

    assert registry.get("oh-project").source == "project"  # type: ignore[union-attr]
    assert registry.get("agents-project").source == "project"  # type: ignore[union-attr]
    assert registry.get("claude-project").source == "project"  # type: ignore[union-attr]


def test_project_skills_can_be_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    _write_skill(repo / ".claude" / "skills", "project-only")

    registry = load_skill_registry(repo, settings=Settings(allow_project_skills=False))

    assert registry.get("project-only") is None


def test_project_skill_discovery_walks_up_to_git_root(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    repo = tmp_path / "repo"
    cwd = repo / "packages" / "api" / "src"
    cwd.mkdir(parents=True)
    (repo / ".git").mkdir()
    root_skill_dir = repo / ".claude" / "skills"
    package_skill_dir = repo / "packages" / ".agents" / "skills"
    outside_skill_dir = tmp_path / ".claude" / "skills"
    root_skill_dir.mkdir(parents=True)
    package_skill_dir.mkdir(parents=True)
    outside_skill_dir.mkdir(parents=True)

    dirs = discover_project_skill_dirs(cwd)

    assert root_skill_dir.resolve() in dirs
    assert package_skill_dir.resolve() in dirs
    assert outside_skill_dir.resolve() not in dirs
    assert dirs.index(root_skill_dir.resolve()) < dirs.index(package_skill_dir.resolve())


def test_project_skill_nearer_cwd_overrides_parent_and_user(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    _write_skill(tmp_path / "home" / ".claude" / "skills", "deploy", "# user deploy\nuser version\n")
    repo = tmp_path / "repo"
    cwd = repo / "services" / "api"
    cwd.mkdir(parents=True)
    (repo / ".git").mkdir()
    _write_skill(repo / ".claude" / "skills", "deploy", "# root deploy\nroot version\n")
    _write_skill(cwd / ".claude" / "skills", "deploy", "# api deploy\napi version\n")

    registry = load_skill_registry(cwd, settings=Settings())
    skill = registry.get("deploy")

    assert skill is not None
    assert skill.source == "project"
    assert "api version" in skill.content


def test_unsafe_project_skill_dirs_are_ignored(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    repo = tmp_path / "repo"
    repo.mkdir()
    escaped = tmp_path / "escaped" / "skills"
    escaped.mkdir(parents=True)

    dirs = discover_project_skill_dirs(repo, ["../escaped/skills", str(escaped), ".claude/skills"])

    assert escaped.resolve() not in dirs


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


# --- bundled skill frontmatter tests ---
#
# The bundled skill loader used to use a naive line-by-line parser that did
# not understand YAML block scalars (``>`` / ``|``) — a partial fix landed in
# #96 only on the user-skill side. These cases pin the bundled loader to the
# same behavior so future bundled skills with frontmatter parse correctly.


def test_bundled_frontmatter_folded_block_scalar():
    """Bundled loader expands folded block scalars the same way user loader does."""
    content = textwrap.dedent("""\
        ---
        name: bundled-folded
        description: >
          A long folded description spanning
          multiple lines that should join with spaces.
        ---

        # Body
    """)
    name, desc = parse_bundled_frontmatter("fallback", content)
    assert name == "bundled-folded"
    assert "A long folded description spanning" in desc
    assert "join with spaces" in desc
    assert "\n" not in desc


def test_bundled_frontmatter_literal_block_scalar():
    """Bundled loader preserves literal-scalar newlines."""
    content = textwrap.dedent("""\
        ---
        name: bundled-literal
        description: |
          Line one.
          Line two.
        ---

        # Body
    """)
    name, desc = parse_bundled_frontmatter("fallback", content)
    assert name == "bundled-literal"
    assert "Line one." in desc
    assert "Line two." in desc


def test_bundled_frontmatter_inline_description():
    """Inline frontmatter description still works on the bundled side."""
    content = textwrap.dedent("""\
        ---
        name: bundled-inline
        description: A short bundled description
        ---

        # Body
    """)
    name, desc = parse_bundled_frontmatter("fallback", content)
    assert name == "bundled-inline"
    assert desc == "A short bundled description"


def test_bundled_no_description_uses_bundled_prefix():
    """When nothing supplies a description, the bundled fallback prefix is used."""
    name, desc = parse_bundled_frontmatter("fallback", "# OnlyHeading\n")
    assert name == "OnlyHeading"
    assert desc == "Bundled skill: OnlyHeading"


def test_bundled_fallback_heading_and_paragraph():
    """Without frontmatter, the bundled loader falls back to heading + first paragraph."""
    content = "# Bundled Skill\nThis is a bundled body description.\n"
    name, desc = parse_bundled_frontmatter("fallback", content)
    assert name == "Bundled Skill"
    assert desc == "This is a bundled body description."
