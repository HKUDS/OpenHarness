"""Tests for slash command handlers."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import openharness.commands.registry as registry_module
from openharness.commands.registry import CommandContext, create_default_command_registry
from openharness.autopilot import RepoVerificationStep
from openharness.config.paths import get_feedback_log_path, get_project_issue_file, get_project_pr_comments_file
from openharness.config.settings import load_settings, save_settings, Settings
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.engine.query_engine import QueryEngine
from openharness.mcp.types import McpHttpServerConfig, McpStdioServerConfig
from openharness.permissions import PermissionChecker
from openharness.plugins.types import PluginCommandDefinition
from openharness.state import AppState, AppStateStore
from openharness.tasks import get_task_manager
from openharness.tools import create_default_tool_registry


class FakeApiClient:
    async def stream_message(self, request):
        del request
        raise AssertionError("stream_message should not be called in command tests")


def _make_engine(tmp_path: Path) -> QueryEngine:
    return QueryEngine(
        api_client=FakeApiClient(),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(load_settings().permission),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )


def _make_context(tmp_path: Path) -> CommandContext:
    tool_registry = create_default_tool_registry()
    return CommandContext(
        engine=QueryEngine(
            api_client=FakeApiClient(),
            tool_registry=tool_registry,
            permission_checker=PermissionChecker(load_settings().permission),
            cwd=tmp_path,
            model="claude-test",
            system_prompt="system",
        ),
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


@pytest.mark.asyncio
async def test_permissions_command_persists(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    command, args = registry.lookup("/permissions set full_auto")
    assert command is not None

    result = await command.handler(args, CommandContext(engine=_make_engine(tmp_path), cwd=str(tmp_path)))

    assert "Auto" in result.message
    assert load_settings().permission.mode == "full_auto"


@pytest.mark.asyncio
async def test_permissions_command_is_marked_local_only(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    command, _ = registry.lookup("/permissions set full_auto")
    assert command is not None
    assert command.remote_invocable is False


@pytest.mark.asyncio
async def test_permissions_command_supports_explicit_remote_admin_opt_in(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    command, _ = registry.lookup("/permissions set full_auto")
    assert command is not None
    assert getattr(command, "remote_admin_opt_in", False) is True


@pytest.mark.asyncio
async def test_plugin_command_is_marked_local_only(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    command, _ = registry.lookup("/plugin list")
    assert command is not None
    assert command.remote_invocable is False


@pytest.mark.asyncio
async def test_plugin_command_supports_explicit_remote_admin_opt_in(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    command, _ = registry.lookup("/plugin list")
    assert command is not None
    assert getattr(command, "remote_admin_opt_in", False) is True


@pytest.mark.asyncio
async def test_reload_plugins_command_is_marked_local_only(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    command, _ = registry.lookup("/reload-plugins")
    assert command is not None
    assert command.remote_invocable is False


@pytest.mark.asyncio
async def test_reload_plugins_command_supports_explicit_remote_admin_opt_in(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    command, _ = registry.lookup("/reload-plugins")
    assert command is not None
    assert getattr(command, "remote_admin_opt_in", False) is True


@pytest.mark.asyncio
async def test_memory_show_rejects_path_traversal(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    registry = create_default_command_registry()
    command, args = registry.lookup("/memory show ../../../../../../etc/hosts")
    assert command is not None

    result = await command.handler(args, CommandContext(engine=_make_engine(tmp_path), cwd=str(tmp_path)))

    assert result.message == "Memory entry path must stay within the project memory directory."


@pytest.mark.asyncio
async def test_memory_show_reads_normal_entries_with_md_fallback(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    registry = create_default_command_registry()

    add_command, add_args = registry.lookup("/memory add Notes :: hello world")
    assert add_command is not None
    await add_command.handler(add_args, CommandContext(engine=_make_engine(tmp_path), cwd=str(tmp_path)))

    show_command, show_args = registry.lookup("/memory show Notes")
    result = await show_command.handler(show_args, CommandContext(engine=_make_engine(tmp_path), cwd=str(tmp_path)))

    assert "hello world" in result.message


@pytest.mark.asyncio
async def test_model_command_persists(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    command, args = registry.lookup("/model opus")
    assert command is not None

    result = await command.handler(args, CommandContext(engine=_make_engine(tmp_path), cwd=str(tmp_path)))

    assert "opus" in result.message
    assert load_settings().resolve_profile()[1].last_model == "opus"
    assert load_settings().model == "claude-opus-4-6"


@pytest.mark.asyncio
async def test_model_command_accepts_direct_value(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    command, args = registry.lookup("/model gpt-5.4")
    assert command is not None

    result = await command.handler(args, CommandContext(engine=_make_engine(tmp_path), cwd=str(tmp_path)))

    assert "gpt-5.4" in result.message
    assert load_settings().model == "gpt-5.4"


@pytest.mark.asyncio
async def test_model_command_default_clears_profile_override(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    save_settings(
        Settings().model_copy(
            update={
                "active_profile": "claude-api",
                "profiles": {
                    "claude-api": {
                        "label": "Claude API",
                        "provider": "anthropic",
                        "api_format": "anthropic",
                        "auth_source": "anthropic_api_key",
                        "default_model": "sonnet",
                        "last_model": "opus",
                    }
                },
            }
        )
    )
    registry = create_default_command_registry()
    command, args = registry.lookup("/model default")
    assert command is not None

    result = await command.handler(args, CommandContext(engine=_make_engine(tmp_path), cwd=str(tmp_path)))

    assert "reset to default" in result.message
    assert load_settings().resolve_profile()[1].last_model == ""
    assert load_settings().model == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_turns_show_reports_unlimited_engine_when_session_is_unbounded(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    context = _make_context(tmp_path)
    context.engine.set_max_turns(None)

    command, args = registry.lookup("/turns show")
    assert command is not None

    result = await command.handler(args, context)

    assert "Max turns (engine): unlimited" in result.message


@pytest.mark.asyncio
async def test_turns_command_accepts_unlimited(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    context = _make_context(tmp_path)

    command, args = registry.lookup("/turns unlimited")
    assert command is not None

    result = await command.handler(args, context)

    assert "unlimited for this session" in result.message
    assert context.engine.max_turns is None


@pytest.mark.asyncio
async def test_provider_command_switches_profile_and_requests_runtime_refresh(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    save_settings(
        Settings().model_copy(
            update={
                "profiles": {
                    "kimi-anthropic": {
                        "label": "Kimi Anthropic",
                        "provider": "anthropic",
                        "api_format": "anthropic",
                        "auth_source": "anthropic_api_key",
                        "default_model": "kimi-k2.5",
                        "last_model": "kimi-k2.5",
                        "base_url": "https://api.moonshot.cn/anthropic",
                        "allowed_models": ["kimi-k2.5"],
                    }
                }
            }
        )
    )
    registry = create_default_command_registry()
    context = _make_context(tmp_path)

    command, args = registry.lookup("/provider kimi-anthropic")
    assert command is not None

    result = await command.handler(args, context)

    loaded = load_settings()
    assert result.refresh_runtime is True
    assert loaded.active_profile == "kimi-anthropic"
    assert loaded.base_url == "https://api.moonshot.cn/anthropic"
    assert loaded.model == "kimi-k2.5"


@pytest.mark.asyncio
async def test_autopilot_command_add_list_and_complete(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    context = _make_context(tmp_path)

    add_command, add_args = registry.lookup("/autopilot add idea Build unified queue :: intake from issues and prs")
    assert add_command is not None
    add_result = await add_command.handler(add_args, context)
    assert "Queued autopilot card" in add_result.message

    list_command, list_args = registry.lookup("/autopilot list")
    assert list_command is not None
    list_result = await list_command.handler(list_args, context)
    assert "Build unified queue" in list_result.message

    next_command, next_args = registry.lookup("/autopilot next")
    next_result = await next_command.handler(next_args, context)
    assert "Build unified queue" in next_result.message
    card_id = next_result.message.split()[0]

    complete_command, complete_args = registry.lookup(f"/autopilot complete {card_id} implemented")
    complete_result = await complete_command.handler(complete_args, context)
    assert "-> completed" in complete_result.message

    status_command, status_args = registry.lookup("/autopilot status")
    status_result = await status_command.handler(status_args, context)
    assert "- completed: 1" in status_result.message


@pytest.mark.asyncio
async def test_autopilot_command_export_dashboard(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    context = _make_context(tmp_path)

    command, args = registry.lookup("/autopilot export-dashboard")
    assert command is not None
    result = await command.handler(args, context)

    assert "Exported autopilot dashboard:" in result.message
    output_dir = Path(result.message.split(": ", 1)[1])
    assert (output_dir / "index.html").exists()
    assert (output_dir / "snapshot.json").exists()


@pytest.mark.asyncio
async def test_ship_command_queues_and_executes_card(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    context = _make_context(tmp_path)

    async def fake_run_agent_prompt(self, prompt: str, *, model, max_turns, permission_mode, cwd=None):
        return "Implemented the requested feature."

    def fake_run_verification_steps(self, policies, *, cwd=None):
        return [RepoVerificationStep(command="uv run pytest -q", returncode=0, status="success")]

    monkeypatch.setattr(
        "openharness.autopilot.service.RepoAutopilotStore._run_agent_prompt",
        fake_run_agent_prompt,
    )
    monkeypatch.setattr(
        "openharness.autopilot.service.RepoAutopilotStore._run_verification_steps",
        fake_run_verification_steps,
    )

    command, args = registry.lookup("/ship Build autopilot tick :: end-to-end automation")
    assert command is not None
    result = await command.handler(args, context)

    assert "-> completed" in result.message
    assert "run report:" in result.message
    assert "verification report:" in result.message


@pytest.mark.asyncio
async def test_plugin_command_registers_and_submits_prompt(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry(
        plugin_commands=[
            PluginCommandDefinition(
                name="fixture:ops:restart",
                description="Restart services safely",
                content="Base workflow\n\n$ARGUMENTS",
                user_invocable=True,
            )
        ]
    )
    command, args = registry.lookup("/fixture:ops:restart api")
    assert command is not None

    result = await command.handler(args, _make_context(tmp_path))

    assert result.submit_prompt == "Base workflow\n\napi"


@pytest.mark.asyncio
async def test_model_command_rejects_values_outside_profile_allowlist(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    save_settings(
        Settings().model_copy(
            update={
                "active_profile": "kimi-anthropic",
                "profiles": {
                    "kimi-anthropic": {
                        "label": "Kimi Anthropic",
                        "provider": "anthropic",
                        "api_format": "anthropic",
                        "auth_source": "anthropic_api_key",
                        "default_model": "kimi-k2.5",
                        "last_model": "kimi-k2.5",
                        "base_url": "https://api.moonshot.cn/anthropic",
                        "allowed_models": ["kimi-k2.5"],
                    }
                },
            }
        )
    )
    registry = create_default_command_registry()
    command, args = registry.lookup("/model claude-opus-4-6")
    assert command is not None

    result = await command.handler(args, CommandContext(engine=_make_engine(tmp_path), cwd=str(tmp_path)))

    assert "is not allowed for profile 'kimi-anthropic'" in result.message


@pytest.mark.asyncio
async def test_doctor_command_reports_context(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    command, args = registry.lookup("/doctor")
    assert command is not None

    result = await command.handler(
        args,
        CommandContext(
            engine=_make_engine(tmp_path),
            cwd=str(tmp_path),
            plugin_summary="Plugins:\n- demo [enabled] Example",
            mcp_summary="No MCP servers configured.",
        ),
    )

    assert "Doctor summary:" in result.message
    assert str(tmp_path) in result.message


@pytest.mark.asyncio
async def test_memory_command_manages_entries(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    registry = create_default_command_registry()
    context = _make_context(tmp_path)

    add_command, add_args = registry.lookup("/memory add Pytest Tips :: use fixtures")
    add_result = await add_command.handler(add_args, context)
    assert "Added memory entry" in add_result.message

    list_command, list_args = registry.lookup("/memory list")
    list_result = await list_command.handler(list_args, context)
    assert "pytest_tips.md" in list_result.message

    show_command, show_args = registry.lookup("/memory show pytest_tips")
    show_result = await show_command.handler(show_args, context)
    assert "use fixtures" in show_result.message

    remove_command, remove_args = registry.lookup("/memory remove pytest_tips")
    remove_result = await remove_command.handler(remove_args, context)
    assert "Removed memory entry" in remove_result.message


@pytest.mark.asyncio
async def test_compact_summary_and_usage_commands(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    context = _make_context(tmp_path)
    context.engine.load_messages(
        [
            ConversationMessage(role="user", content=[TextBlock(text="alpha request")]),
            ConversationMessage(role="assistant", content=[TextBlock(text="alpha reply")]),
            ConversationMessage(role="user", content=[TextBlock(text="beta request")]),
            ConversationMessage(role="assistant", content=[TextBlock(text="beta reply")]),
        ]
    )

    summary_command, summary_args = registry.lookup("/summary 3")
    summary_result = await summary_command.handler(summary_args, context)
    assert "assistant: alpha reply" in summary_result.message or "user: beta request" in summary_result.message

    compact_command, compact_args = registry.lookup("/compact 2")
    compact_result = await compact_command.handler(compact_args, context)
    assert "Compacted conversation" in compact_result.message
    assert len(context.engine.messages) == 3

    usage_command, usage_args = registry.lookup("/usage")
    usage_result = await usage_command.handler(usage_args, context)
    assert "Estimated conversation tokens" in usage_result.message

    stats_command, stats_args = registry.lookup("/stats")
    stats_result = await stats_command.handler(stats_args, context)
    assert "Session stats:" in stats_result.message


@pytest.mark.asyncio
async def test_ui_mode_commands_persist_and_update_state(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    registry = create_default_command_registry()
    context = _make_context(tmp_path)

    config_command, config_args = registry.lookup("/config set verbose true")
    config_result = await config_command.handler(config_args, context)
    assert "Updated verbose" in config_result.message
    assert load_settings().verbose is True

    output_command, output_args = registry.lookup("/output-style set minimal")
    output_result = await output_command.handler(output_args, context)
    assert "minimal" in output_result.message
    assert context.app_state.get().output_style == "minimal"

    keybindings_command, keybindings_args = registry.lookup("/keybindings")
    keybindings_result = await keybindings_command.handler(keybindings_args, context)
    assert "ctrl+l" in keybindings_result.message

    vim_command, vim_args = registry.lookup("/vim toggle")
    vim_result = await vim_command.handler(vim_args, context)
    assert "enabled" in vim_result.message
    assert context.app_state.get().vim_enabled is True

    voice_command, voice_args = registry.lookup("/voice keyterms Shipping pytest fixtures")
    voice_result = await voice_command.handler(voice_args, context)
    assert "pytest" in voice_result.message

    plan_command, plan_args = registry.lookup("/plan on")
    plan_result = await plan_command.handler(plan_args, context)
    assert "enabled" in plan_result.message
    assert load_settings().permission.mode == "plan"

    fast_command, fast_args = registry.lookup("/fast on")
    fast_result = await fast_command.handler(fast_args, context)
    assert "enabled" in fast_result.message
    assert load_settings().fast_mode is True
    assert context.app_state.get().fast_mode is True

    effort_command, effort_args = registry.lookup("/effort high")
    effort_result = await effort_command.handler(effort_args, context)
    assert "high" in effort_result.message
    assert load_settings().effort == "high"
    assert context.app_state.get().effort == "high"

    passes_command, passes_args = registry.lookup("/passes 3")
    passes_result = await passes_command.handler(passes_args, context)
    assert "3" in passes_result.message
    assert load_settings().passes == 3
    assert context.app_state.get().passes == 3


@pytest.mark.asyncio
async def test_version_context_and_share_commands(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    registry = create_default_command_registry()
    context = _make_context(tmp_path)

    version_command, version_args = registry.lookup("/version")
    version_result = await version_command.handler(version_args, context)
    assert "OpenHarness" in version_result.message

    context_command, context_args = registry.lookup("/context")
    context_result = await context_command.handler(context_args, context)
    assert "OpenHarness" in context_result.message or "interactive agent" in context_result.message

    share_command, share_args = registry.lookup("/share")
    share_result = await share_command.handler(share_args, context)
    assert "shareable transcript snapshot" in share_result.message


@pytest.mark.asyncio
async def test_auth_feedback_and_project_context_commands(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    registry = create_default_command_registry()
    context = _make_context(tmp_path)

    login_command, login_args = registry.lookup("/login sk-test-123456")
    login_result = await login_command.handler(login_args, context)
    assert "Stored API key" in login_result.message
    assert load_settings().api_key == "sk-test-123456"

    issue_command, issue_args = registry.lookup("/issue set Fix CI :: The CI flakes on task retry")
    issue_result = await issue_command.handler(issue_args, context)
    assert "Saved issue context" in issue_result.message
    assert "Fix CI" in get_project_issue_file(tmp_path).read_text(encoding="utf-8")

    pr_command, pr_args = registry.lookup("/pr_comments add src/app.py:12 :: simplify this branch")
    pr_result = await pr_command.handler(pr_args, context)
    assert "Added PR comment" in pr_result.message
    assert "simplify this branch" in get_project_pr_comments_file(tmp_path).read_text(encoding="utf-8")

    feedback_command, feedback_args = registry.lookup("/feedback this workflow feels good")
    feedback_result = await feedback_command.handler(feedback_args, context)
    assert "Saved feedback" in feedback_result.message
    assert "this workflow feels good" in get_feedback_log_path().read_text(encoding="utf-8")

    logout_command, logout_args = registry.lookup("/logout")
    logout_result = await logout_command.handler(logout_args, context)
    assert "Cleared stored API key" in logout_result.message
    assert load_settings().api_key == ""


@pytest.mark.asyncio
async def test_agents_session_files_and_reload_plugins_commands(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    registry = create_default_command_registry()
    context = _make_context(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")

    session_command, session_args = registry.lookup("/session")
    session_result = await session_command.handler(session_args, context)
    assert "Session directory:" in session_result.message

    session_path_command, session_path_args = registry.lookup("/session path")
    session_path_result = await session_path_command.handler(session_path_args, context)
    assert "sessions" in session_path_result.message

    session_tag_command, session_tag_args = registry.lookup("/session tag smoke")
    session_tag_result = await session_tag_command.handler(session_tag_args, context)
    assert "smoke.json" in session_tag_result.message
    assert "smoke.md" in session_tag_result.message

    tag_command, tag_args = registry.lookup("/tag alias-smoke")
    tag_result = await tag_command.handler(tag_args, context)
    assert "alias-smoke.json" in tag_result.message
    assert "alias-smoke.md" in tag_result.message

    files_command, files_args = registry.lookup("/files app.py")
    files_result = await files_command.handler(files_args, context)
    assert "src/app.py" in files_result.message

    files_dirs_command, files_dirs_args = registry.lookup("/files dirs")
    files_dirs_result = await files_dirs_command.handler(files_dirs_args, context)
    assert "src" in files_dirs_result.message

    plugin_root = tmp_path / "config" / "plugins" / "fixture-plugin"
    (plugin_root / "skills").mkdir(parents=True)
    (plugin_root / "plugin.json").write_text(
        '{"name":"fixture-plugin","version":"1.0.0","description":"Fixture plugin"}',
        encoding="utf-8",
    )
    reload_command, reload_args = registry.lookup("/reload-plugins")
    reload_result = await reload_command.handler(reload_args, context)
    assert "fixture-plugin" in reload_result.message

    manager = get_task_manager()
    task = await manager.create_agent_task(
        prompt="ready",
        description="test agent",
        cwd=tmp_path,
        command="python -u -c \"import sys; print(sys.stdin.readline().strip())\"",
    )
    agents_command, agents_args = registry.lookup("/agents")
    agents_result = await agents_command.handler(agents_args, context)
    assert task.id in agents_result.message

    agent_show_command, agent_show_args = registry.lookup(f"/agents show {task.id}")
    agent_show_result = await agent_show_command.handler(agent_show_args, context)
    assert "test agent" in agent_show_result.message


@pytest.mark.asyncio
async def test_agents_help_and_subagents_alias(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    registry = create_default_command_registry()
    context = _make_context(tmp_path)

    agents_help_command, agents_help_args = registry.lookup("/agents help")
    assert agents_help_command is not None
    agents_help_result = await agents_help_command.handler(agents_help_args, context)
    assert "Subagent guide:" in agents_help_result.message
    assert 'subagent_type="worker"' in agents_help_result.message

    subagents_command, subagents_args = registry.lookup("/subagents")
    assert subagents_command is not None
    subagents_result = await subagents_command.handler(subagents_args, context)
    assert "Subagent guide:" in subagents_result.message

    agents_command, agents_args = registry.lookup("/agents")
    assert agents_command is not None
    agents_result = await agents_command.handler(agents_args, context)
    assert "Subagent guide:" in agents_result.message


@pytest.mark.asyncio
async def test_init_and_bridge_commands(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    registry = create_default_command_registry()
    context = _make_context(tmp_path)

    init_command, init_args = registry.lookup("/init")
    init_result = await init_command.handler(init_args, context)
    assert "Initialized project files" in init_result.message or "already initialized" in init_result.message
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".openharness" / "memory" / "MEMORY.md").exists()

    bridge_show_command, bridge_show_args = registry.lookup("/bridge show")
    bridge_show_result = await bridge_show_command.handler(bridge_show_args, context)
    assert "Bridge summary:" in bridge_show_result.message

    bridge_encode_command, bridge_encode_args = registry.lookup("/bridge encode https://api.example.com token123")
    bridge_encode_result = await bridge_encode_command.handler(bridge_encode_args, context)
    assert bridge_encode_result.message

    bridge_decode_command, bridge_decode_args = registry.lookup(f"/bridge decode {bridge_encode_result.message}")
    bridge_decode_result = await bridge_decode_command.handler(bridge_decode_args, context)
    assert "api.example.com" in bridge_decode_result.message

    bridge_sdk_command, bridge_sdk_args = registry.lookup("/bridge sdk https://api.example.com session123")
    bridge_sdk_result = await bridge_sdk_command.handler(bridge_sdk_args, context)
    assert "session123" in bridge_sdk_result.message

    bridge_spawn_command, bridge_spawn_args = registry.lookup("/bridge spawn printf bridge-ok")
    bridge_spawn_result = await bridge_spawn_command.handler(bridge_spawn_args, context)
    assert "Spawned bridge session" in bridge_spawn_result.message
    session_id = bridge_spawn_result.message.split()[3]

    bridge_list_command, bridge_list_args = registry.lookup("/bridge list")
    bridge_list_result = await bridge_list_command.handler(bridge_list_args, context)
    assert session_id in bridge_list_result.message

    bridge_output_command, bridge_output_args = registry.lookup(f"/bridge output {session_id}")
    bridge_output_result = await bridge_output_command.handler(bridge_output_args, context)
    assert "bridge-ok" in bridge_output_result.message or bridge_output_result.message == "(no output)"

    bridge_stop_command, bridge_stop_args = registry.lookup(f"/bridge stop {session_id}")
    bridge_stop_result = await bridge_stop_command.handler(bridge_stop_args, context)
    assert f"Stopped bridge session {session_id}" in bridge_stop_result.message


@pytest.mark.asyncio
async def test_copy_rewind_and_meta_commands(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    registry = create_default_command_registry()
    context = _make_context(tmp_path)
    context.engine.load_messages(
        [
            ConversationMessage.from_user_text("first prompt"),
            ConversationMessage(role="assistant", content=[TextBlock(text="first answer")]),
            ConversationMessage.from_user_text("second prompt"),
            ConversationMessage(role="assistant", content=[TextBlock(text="second answer")]),
        ]
    )

    copied: list[str] = []

    def _fake_copy(text: str) -> None:
        copied.append(text)

    monkeypatch.setattr(registry_module.pyperclip, "copy", _fake_copy)

    copy_command, copy_args = registry.lookup("/copy")
    copy_result = await copy_command.handler(copy_args, context)
    assert "Copied" in copy_result.message
    assert copied == ["second answer"]

    rewind_command, rewind_args = registry.lookup("/rewind 1")
    rewind_result = await rewind_command.handler(rewind_args, context)
    assert "removed 2 message(s)" in rewind_result.message
    assert len(context.engine.messages) == 2

    privacy_command, privacy_args = registry.lookup("/privacy-settings")
    privacy_result = await privacy_command.handler(privacy_args, context)
    assert "user_config_dir" in privacy_result.message

    rate_command, rate_args = registry.lookup("/rate-limit-options")
    rate_result = await rate_command.handler(rate_args, context)
    assert "Rate limit options:" in rate_result.message

    release_command, release_args = registry.lookup("/release-notes")
    release_result = await release_command.handler(release_args, context)
    assert "Release Notes" in release_result.message

    upgrade_command, upgrade_args = registry.lookup("/upgrade")
    upgrade_result = await upgrade_command.handler(upgrade_args, context)
    assert "Upgrade instructions:" in upgrade_result.message


@pytest.mark.asyncio
async def test_mcp_and_voice_commands_report_richer_state(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    settings = Settings(
        mcp_servers={
            "http-demo": McpHttpServerConfig(url="https://example.com/mcp"),
            "stdio-demo": McpStdioServerConfig(command="python", args=["-m", "demo"]),
        }
    )
    save_settings(settings)

    registry = create_default_command_registry()
    context = _make_context(tmp_path)

    mcp_http_command, mcp_http_args = registry.lookup("/mcp auth http-demo secret-token")
    mcp_http_result = await mcp_http_command.handler(mcp_http_args, context)
    assert "Saved MCP auth for http-demo" in mcp_http_result.message
    assert load_settings().mcp_servers["http-demo"].headers["Authorization"] == "Bearer secret-token"

    mcp_stdio_command, mcp_stdio_args = registry.lookup("/mcp auth stdio-demo env DEMO_TOKEN")
    mcp_stdio_result = await mcp_stdio_command.handler(mcp_stdio_args, context)
    assert "Saved MCP auth for stdio-demo" in mcp_stdio_result.message
    assert load_settings().mcp_servers["stdio-demo"].env["MCP_AUTH_TOKEN"] == "DEMO_TOKEN"

    voice_command, voice_args = registry.lookup("/voice show")
    voice_result = await voice_command.handler(voice_args, context)
    assert "Voice mode:" in voice_result.message
    assert "Available:" in voice_result.message
    assert "Reason:" in voice_result.message


@pytest.mark.asyncio
async def test_git_commands_report_repository_state(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "openharness@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "OpenHarness Tests"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    (tmp_path / "demo.txt").write_text("hello\n", encoding="utf-8")

    registry = create_default_command_registry()
    context = _make_context(tmp_path)

    branch_command, branch_args = registry.lookup("/branch show")
    branch_result = await branch_command.handler(branch_args, context)
    assert "Current branch" in branch_result.message

    diff_command, diff_args = registry.lookup("/diff")
    diff_result = await diff_command.handler(diff_args, context)
    assert "demo.txt" in diff_result.message or "(no diff)" in diff_result.message

    commit_command, commit_args = registry.lookup("/commit initial commit")
    commit_result = await commit_command.handler(commit_args, context)
    assert "commit" in commit_result.message.lower()


def test_quit_is_alias_for_exit():
    """Regression for #183: /quit should resolve to the same handler as /exit."""
    reg = create_default_command_registry()

    exit_cmd, _ = reg.lookup("/exit")
    quit_cmd, _ = reg.lookup("/quit")

    assert exit_cmd is quit_cmd
    assert quit_cmd.name == "exit"


def test_help_and_list_do_not_duplicate_aliases():
    """Aliases share a SlashCommand object; help/listing must not repeat it."""
    reg = create_default_command_registry()

    names = [cmd.name for cmd in reg.list_commands()]
    assert names.count("exit") == 1
    assert "quit" not in names  # alias is resolvable via lookup, not listed

    help_text = reg.help_text()
    assert help_text.count("/exit ") == 1
    assert "/quit" not in help_text
