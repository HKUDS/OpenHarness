from pathlib import Path

from openharness.config.settings import Settings
from openharness.memory import add_memory_entry as add_project_memory_entry
from openharness.prompts import build_runtime_system_prompt

from ohmo.memory import add_memory_entry as add_ohmo_memory_entry
from ohmo.memory import list_memory_files as list_ohmo_memory_files
from ohmo.memory import remove_memory_entry as remove_ohmo_memory_entry
from ohmo.prompts import build_ohmo_system_prompt
from ohmo.workspace import (
    get_bootstrap_path,
    get_identity_path,
    get_soul_path,
    get_user_path,
    initialize_workspace,
)


def test_ohmo_prompt_includes_persona_and_memory(tmp_path: Path):
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)
    get_soul_path(workspace).write_text("# soul\nSpeak like a calm operator.\n", encoding="utf-8")
    get_identity_path(workspace).write_text("# identity\nName: ohmo\n", encoding="utf-8")
    get_user_path(workspace).write_text("# user\nPrefers terse answers.\n", encoding="utf-8")
    get_bootstrap_path(workspace).write_text("# bootstrap\nAsk a few high-value questions.\n", encoding="utf-8")
    add_ohmo_memory_entry(workspace, "timezone", "The user prefers UTC timestamps.")

    prompt = build_ohmo_system_prompt(tmp_path, workspace=workspace)

    assert "You are OpenHarness" in prompt
    assert "Speak like a calm operator." in prompt
    assert "Name: ohmo" in prompt
    assert "Prefers terse answers." in prompt
    assert "Ask a few high-value questions." in prompt
    assert "timezone.md" in prompt
    assert "UTC timestamps" in prompt


def test_ohmo_runtime_prompt_can_exclude_project_memory(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)
    add_ohmo_memory_entry(workspace, "personal", "ohmo-only personal fact")
    add_project_memory_entry(tmp_path, "project", "project memory should not leak")

    base_prompt = build_ohmo_system_prompt(tmp_path, workspace=workspace)
    runtime_prompt = build_runtime_system_prompt(
        Settings(system_prompt=base_prompt),
        cwd=tmp_path,
        latest_user_prompt="hello",
        include_project_memory=False,
    )

    assert "ohmo-only personal fact" in runtime_prompt
    assert "project memory should not leak" not in runtime_prompt


def test_ohmo_memory_uses_schema_and_soft_delete(tmp_path: Path):
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)

    path = add_ohmo_memory_entry(workspace, "timezone", "The user prefers UTC timestamps.")

    text = path.read_text(encoding="utf-8")
    assert "schema_version: 1" in text
    assert "type: \"personal\"" in text

    assert remove_ohmo_memory_entry(workspace, "timezone") is True
    assert path.exists()
    assert list_ohmo_memory_files(workspace) == []
    assert "disabled: true" in path.read_text(encoding="utf-8")
