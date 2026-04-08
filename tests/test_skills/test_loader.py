"""Tests for skill loading."""

from __future__ import annotations

from pathlib import Path

from openharness.skills import get_user_skills_dir, load_skill_registry
from openharness.skills.runtime import activate_skill


def test_load_skill_registry_includes_bundled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = load_skill_registry()

    names = [skill.name for skill in registry.list_skills()]
    assert "simplify" in names
    assert "review" in names


def test_load_skill_registry_includes_user_skills(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    skills_dir = get_user_skills_dir()
    (skills_dir / "deploy.md").write_text("# Deploy\nDeployment workflow guidance\n", encoding="utf-8")

    registry = load_skill_registry()
    deploy = registry.get("Deploy")

    assert deploy is not None
    assert deploy.source == "user"
    assert "Deployment workflow guidance" in deploy.content


def test_load_skill_registry_parses_frontmatter_metadata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    skills_dir = get_user_skills_dir()
    (skills_dir / "triage.md").write_text(
        "---\n"
        "name: triage\n"
        "description: Triage incoming issues\n"
        "aliases: [bugtriage, intake]\n"
        "user_invocable: true\n"
        "model_invocable: false\n"
        "allowed_tools: [read_file, grep]\n"
        "model_override: claude-opus-4-6\n"
        "effort_override: high\n"
        "execution_mode: inline\n"
        "---\n\n"
        "# triage\n\nFollow the incident triage workflow.\n",
        encoding="utf-8",
    )

    registry = load_skill_registry()
    skill = registry.get("bugtriage")

    assert skill is not None
    assert skill.name == "triage"
    assert skill.description == "Triage incoming issues"
    assert skill.aliases == ("bugtriage", "intake")
    assert skill.model_invocable is False
    assert skill.allowed_tools == ("read_file", "grep")
    assert skill.model_override == "claude-opus-4-6"
    assert skill.effort_override == "high"
    assert "Follow the incident triage workflow." in skill.instructions


def test_activate_skill_resolves_aliases(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    skills_dir = get_user_skills_dir()
    (skills_dir / "triage.md").write_text(
        "---\nname: triage\naliases: [bugtriage]\n---\n\n# triage\n\nUse triage flow.\n",
        encoding="utf-8",
    )

    active = activate_skill("bugtriage", tmp_path)

    assert active is not None
    assert active.definition.name == "triage"
