"""Tests for CLAUDE.md loading."""

from __future__ import annotations

from pathlib import Path

from openharness.config.paths import get_project_issue_file, get_project_pr_comments_file
from openharness.prompts import build_runtime_system_prompt, discover_claude_md_files, load_claude_md_prompt
from openharness.config.settings import Settings


def test_discover_claude_md_files(tmp_path: Path):
    repo = tmp_path / "repo"
    nested = repo / "pkg" / "mod"
    nested.mkdir(parents=True)
    (repo / "CLAUDE.md").write_text("root instructions", encoding="utf-8")
    rules_dir = repo / ".claude" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "python.md").write_text("rule instructions", encoding="utf-8")

    files = discover_claude_md_files(nested)

    assert repo / "CLAUDE.md" in files
    assert rules_dir / "python.md" in files


def test_load_claude_md_prompt(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CLAUDE.md").write_text("be careful", encoding="utf-8")

    prompt = load_claude_md_prompt(repo)

    assert prompt is not None
    assert "Project Instructions" in prompt
    assert "be careful" in prompt


def test_build_runtime_system_prompt_combines_sections(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CLAUDE.md").write_text("repo rules", encoding="utf-8")

    prompt = build_runtime_system_prompt(Settings(), cwd=repo, latest_user_prompt="hello")

    assert "Environment" in prompt
    assert "Project Instructions" in prompt
    assert "repo rules" in prompt
    assert "Memory" in prompt


def test_build_runtime_system_prompt_includes_project_context_and_fast_mode(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    repo = tmp_path / "repo"
    repo.mkdir()
    get_project_issue_file(repo).write_text("# Bug\nNeed to fix flaky test.\n", encoding="utf-8")
    get_project_pr_comments_file(repo).write_text(
        "# PR Comments\n- app.py:12: Please simplify this branch.\n",
        encoding="utf-8",
    )

    prompt = build_runtime_system_prompt(Settings(fast_mode=True), cwd=repo, latest_user_prompt="fix it")

    assert "Fast mode is enabled" in prompt
    assert "Issue Context" in prompt
    assert "Need to fix flaky test" in prompt
    assert "Pull Request Comments" in prompt
    assert "Please simplify this branch" in prompt


def test_build_runtime_system_prompt_uses_coordinator_prompt_when_enabled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_CODE_COORDINATOR_MODE", "1")
    repo = tmp_path / "repo"
    repo.mkdir()

    prompt = build_runtime_system_prompt(Settings(), cwd=repo, latest_user_prompt="investigate")

    assert "You are a **coordinator**." in prompt
    assert "Coordinator User Context" not in prompt
    assert "Workers spawned via the agent tool have access to these tools" not in prompt
    assert "Environment" not in prompt


def test_build_runtime_system_prompt_skips_coordinator_context_when_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()

    prompt = build_runtime_system_prompt(Settings(), cwd=repo, latest_user_prompt="investigate")

    assert "Coordinator User Context" not in prompt
    assert "You are a **coordinator**." not in prompt
    assert "Environment" in prompt
