"""Higher-level slash command integration flows."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openharness.commands.registry import CommandContext, create_default_command_registry
from openharness.config.settings import load_settings
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.engine.query_engine import QueryEngine
from openharness.permissions import PermissionChecker
from openharness.state import AppState, AppStateStore
from openharness.tools import create_default_tool_registry


class FakeApiClient:
    async def stream_message(self, request):
        del request
        raise AssertionError("stream_message should not be called in command flow tests")


def _build_context(tmp_path: Path) -> CommandContext:
    tool_registry = create_default_tool_registry()
    engine = QueryEngine(
        api_client=FakeApiClient(),
        tool_registry=tool_registry,
        permission_checker=PermissionChecker(load_settings().permission),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )
    engine.load_messages(
        [
            ConversationMessage(role="user", content=[TextBlock(text="first")]),
            ConversationMessage(role="assistant", content=[TextBlock(text="second")]),
            ConversationMessage(role="user", content=[TextBlock(text="third")]),
            ConversationMessage(role="assistant", content=[TextBlock(text="fourth")]),
        ]
    )
    return CommandContext(
        engine=engine,
        cwd=str(tmp_path),
        tool_registry=tool_registry,
        app_state=AppStateStore(
            AppState(
                model="claude-test",
                permission_mode="default",
                theme="default",
                keybindings={},
            )
        ),
    )


def _write_fixture_plugin(root: Path) -> Path:
    plugin_dir = root / "fixture-plugin"
    fixture_skill_dir = plugin_dir / "skills" / "fixture"
    fixture_skill_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"name": "fixture-plugin", "version": "1.0.0", "description": "Fixture plugin"}),
        encoding="utf-8",
    )
    (fixture_skill_dir / "SKILL.md").write_text(
        "# FixtureSkill\nFixture command plugin content.\n",
        encoding="utf-8",
    )
    return plugin_dir


@pytest.mark.asyncio
async def test_command_flow_for_memory_modes_and_tasks(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    registry = create_default_command_registry()
    context = _build_context(tmp_path)

    for raw in [
        "/memory add Notes :: command flow note",
        "/memory list",
        "/summary 4",
        "/compact 2",
        "/plan on",
        "/fast on",
        "/output-style set minimal",
        "/vim on",
        "/voice on",
        "/tasks run printf 'command-flow-task'",
    ]:
        command, args = registry.lookup(raw)
        result = await command.handler(args, context)
        assert result is not None

    output_command, output_args = registry.lookup("/tasks list")
    output_result = await output_command.handler(output_args, context)
    assert "command-flow-task" in output_result.message
    task_id = output_result.message.split()[0]

    update_command, update_args = registry.lookup(f"/tasks update {task_id} progress 40")
    update_result = await update_command.handler(update_args, context)
    assert "40%" in update_result.message

    note_command, note_args = registry.lookup(f"/tasks update {task_id} note waiting on review")
    note_result = await note_command.handler(note_args, context)
    assert "note" in note_result.message

    onboarding_command, onboarding_args = registry.lookup("/onboarding")
    onboarding_result = await onboarding_command.handler(onboarding_args, context)
    assert "quickstart" in onboarding_result.message.lower()

    issue_command, issue_args = registry.lookup("/issue set Command Flow :: Needs review")
    issue_result = await issue_command.handler(issue_args, context)
    assert "Saved issue context" in issue_result.message

    pr_command, pr_args = registry.lookup("/pr_comments add README.md:1 :: tighten wording")
    pr_result = await pr_command.handler(pr_args, context)
    assert "Added PR comment" in pr_result.message

    doctor_command, doctor_args = registry.lookup("/doctor")
    doctor_result = await doctor_command.handler(doctor_args, context)
    assert "- output_style: minimal" in doctor_result.message
    assert "- vim_mode: on" in doctor_result.message
    assert "- voice_mode: on" in doctor_result.message
    assert load_settings().fast_mode is True
    assert context.app_state.get().fast_mode is True


@pytest.mark.asyncio
async def test_plugin_command_lifecycle_flow(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    context = _build_context(tmp_path)
    plugin_source = _write_fixture_plugin(tmp_path / "plugin-source")

    install_command, install_args = registry.lookup(f"/plugin install {plugin_source}")
    install_result = await install_command.handler(install_args, context)
    assert "Installed plugin" in install_result.message

    disable_command, disable_args = registry.lookup("/plugin disable fixture-plugin")
    disable_result = await disable_command.handler(disable_args, context)
    assert "Disabled plugin" in disable_result.message
    assert load_settings().enabled_plugins["fixture-plugin"] is False

    enable_command, enable_args = registry.lookup("/plugin enable fixture-plugin")
    enable_result = await enable_command.handler(enable_args, context)
    assert "Enabled plugin" in enable_result.message
    assert load_settings().enabled_plugins["fixture-plugin"] is True

    uninstall_command, uninstall_args = registry.lookup("/plugin uninstall fixture-plugin")
    uninstall_result = await uninstall_command.handler(uninstall_args, context)
    assert "Uninstalled plugin" in uninstall_result.message


@pytest.mark.asyncio
async def test_plugin_command_rejects_traversal_uninstall_without_deleting_sibling(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    context = _build_context(tmp_path)
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "marker.txt").write_text("keep", encoding="utf-8")

    uninstall_command, uninstall_args = registry.lookup("/plugin uninstall ../../victim")
    uninstall_result = await uninstall_command.handler(uninstall_args, context)

    assert "Invalid plugin name" in uninstall_result.message
    assert victim.exists()
    assert (victim / "marker.txt").read_text(encoding="utf-8") == "keep"
