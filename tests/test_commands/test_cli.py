"""CLI smoke tests."""

import json
import re
import sys
import types
from pathlib import Path

from typer.testing import CliRunner

import openharness.cli as cli
from openharness.config import load_settings
from openharness.config.settings import Settings
from openharness.mcp.types import McpStdioServerConfig


app = cli.app


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["--help"],
        env={"NO_COLOR": "1", "COLUMNS": "160"},
    )
    plain_output = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert result.exit_code == 0
    assert "Oh my Harness!" in plain_output
    assert "setup" in plain_output
    assert "--dry-run" in plain_output


def test_setup_flow_selects_profile_and_model(tmp_path: Path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path))

    selected = []

    def fake_select(statuses, default_value=None):
        selected.append((tuple(statuses.keys()), default_value))
        return "codex"

    logged_in = []

    def fake_login(provider):
        logged_in.append(provider)

    monkeypatch.setattr("openharness.cli._select_setup_workflow", fake_select)
    monkeypatch.setattr("openharness.cli._prompt_model_for_profile", lambda profile: "gpt-5.4")
    monkeypatch.setattr("openharness.cli._login_provider", fake_login)

    result = runner.invoke(app, ["setup"])
    assert result.exit_code == 0
    assert "Setup complete:" in result.output
    assert logged_in == ["openai_codex"]

    settings = load_settings()
    assert settings.active_profile == "codex"
    assert settings.resolve_profile()[1].last_model == "gpt-5.4"


def test_select_from_menu_uses_questionary_when_tty(monkeypatch):
    answers = []

    class _Prompt:
        def ask(self):
            return "codex"

    fake_questionary = types.SimpleNamespace(
        Choice=lambda title, value, checked=False: {
            "title": title,
            "value": value,
            "checked": checked,
        },
        select=lambda title, choices, default=None: answers.append((title, choices, default)) or _Prompt(),
    )

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(cli.sys, "__stdin__", sys.stdin)
    monkeypatch.setattr(cli.sys, "__stdout__", sys.stdout)
    monkeypatch.setitem(sys.modules, "questionary", fake_questionary)

    result = cli._select_from_menu(
        "Choose a provider workflow:",
        [("codex", "Codex"), ("claude-api", "Claude API")],
        default_value="codex",
    )

    assert result == "codex"
    assert answers


def test_setup_flow_creates_kimi_profile_with_profile_scoped_key(tmp_path: Path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path))
    # Prevent env var leakage from overriding the configured api_key
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    selections = iter(["claude-api", "kimi-anthropic"])
    prompts = iter(
        [
            "https://api.moonshot.cn/anthropic",
            "kimi-k2.5",
        ]
    )

    monkeypatch.setattr("openharness.cli._select_setup_workflow", lambda *args, **kwargs: next(selections))
    monkeypatch.setattr("openharness.cli._select_from_menu", lambda *args, **kwargs: next(selections))
    monkeypatch.setattr("openharness.cli._text_prompt", lambda *args, **kwargs: next(prompts))
    monkeypatch.setattr("openharness.auth.flows.ApiKeyFlow.run", lambda self: "sk-kimi-test")

    result = runner.invoke(app, ["setup"])
    assert result.exit_code == 0
    assert "Setup complete:" in result.output
    assert "- profile: kimi-anthropic" in result.output

    settings = load_settings()
    assert settings.active_profile == "kimi-anthropic"
    profile = settings.resolve_profile()[1]
    assert profile.base_url == "https://api.moonshot.cn/anthropic"
    assert profile.credential_slot == "kimi-anthropic"
    assert profile.allowed_models == ["kimi-k2.5"]

    from openharness.auth.storage import load_credential

    assert load_credential("profile:kimi-anthropic", "api_key") == "sk-kimi-test"


def test_dangerously_skip_permissions_passes_full_auto_to_run_repl(monkeypatch):
    runner = CliRunner()
    captured = {}

    async def fake_run_repl(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("openharness.ui.app.run_repl", fake_run_repl)

    result = runner.invoke(app, ["--dangerously-skip-permissions"])

    assert result.exit_code == 0
    assert captured["permission_mode"] == "full_auto"


def test_task_worker_flag_routes_to_run_task_worker(monkeypatch):
    runner = CliRunner()
    captured = {}

    async def fake_run_task_worker(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("openharness.ui.app.run_task_worker", fake_run_task_worker)

    result = runner.invoke(app, ["--task-worker", "--model", "kimi-k2.5"])

    assert result.exit_code == 0
    assert captured["model"] == "kimi-k2.5"


def test_dry_run_uses_preview_builder_and_skips_repl(monkeypatch):
    runner = CliRunner()
    captured = {}

    def fake_build_dry_run_preview(**kwargs):
        captured.update(kwargs)
        return {
            "cwd": kwargs["cwd"],
            "prompt_preview": kwargs["prompt"],
            "settings": {
                "active_profile": "claude-api",
                "profile_label": "Claude API",
                "provider": "anthropic",
                "api_format": "anthropic",
                "model": "claude-sonnet-4-6",
                "base_url": "",
                "permission_mode": "default",
                "max_turns": 200,
                "effort": "medium",
                "passes": 1,
            },
            "validation": {
                "auth_status": "configured",
                "api_client": {"status": "ok"},
                "system_prompt_chars": 123,
                "mcp_validation": "skipped",
            },
            "entrypoint": {"kind": "model_prompt", "detail": "preview only"},
            "plugins": [],
            "skills": [],
            "commands": [],
            "tools": [],
            "mcp_servers": [],
            "system_prompt_preview": "preview",
        }

    async def fake_run_repl(**kwargs):  # pragma: no cover - should never be called
        raise AssertionError(f"run_repl should not be called during dry-run: {kwargs}")

    monkeypatch.setattr("openharness.cli._build_dry_run_preview", fake_build_dry_run_preview)
    monkeypatch.setattr("openharness.ui.app.run_repl", fake_run_repl)

    result = runner.invoke(app, ["--dry-run", "--print", "ship it", "--model", "gpt-5.4"])

    assert result.exit_code == 0
    assert captured["prompt"] == "ship it"
    assert captured["model"] == "gpt-5.4"
    assert "OpenHarness Dry Run" in result.output
    assert "ship it" in result.output


def test_dry_run_json_output(monkeypatch):
    runner = CliRunner()

    def fake_build_dry_run_preview(**kwargs):
        return {
            "mode": "dry-run",
            "cwd": kwargs["cwd"],
            "prompt": kwargs["prompt"],
            "prompt_preview": kwargs["prompt"],
            "settings": {
                "active_profile": "claude-api",
                "profile_label": "Claude API",
                "provider": "anthropic",
                "api_format": "anthropic",
                "model": "claude-sonnet-4-6",
                "base_url": "",
                "permission_mode": "default",
                "max_turns": 200,
                "effort": "medium",
                "passes": 1,
            },
            "validation": {
                "auth_status": "configured",
                "api_client": {"status": "ok"},
                "system_prompt_chars": 123,
                "mcp_validation": "skipped",
            },
            "entrypoint": {"kind": "interactive_session", "detail": "wait"},
            "plugins": [],
            "skills": [],
            "commands": [],
            "tools": [],
            "mcp_servers": [],
            "system_prompt_preview": "preview",
        }

    monkeypatch.setattr("openharness.cli._build_dry_run_preview", fake_build_dry_run_preview)

    result = runner.invoke(app, ["--dry-run", "--output-format", "json", "--print", "preview this"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["mode"] == "dry-run"
    assert payload["prompt"] == "preview this"


def test_dry_run_rejects_continue_resume(monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("openharness.cli._build_dry_run_preview", lambda **kwargs: {"mode": "dry-run"})

    result = runner.invoke(app, ["--dry-run", "--continue"])

    assert result.exit_code == 1
    assert "--dry-run does not support --continue/--resume yet" in result.output


def test_build_dry_run_preview_classifies_slash_command_and_flags_bad_mcp(monkeypatch, tmp_path: Path):
    settings = Settings(
        api_key="sk-test",
        mcp_servers={
            "broken": McpStdioServerConfig(command="definitely-not-a-real-command-openharness"),
        },
    )

    class _FakeSkillRegistry:
        def list_skills(self):
            return []

    monkeypatch.setattr("openharness.config.load_settings", lambda: settings)
    monkeypatch.setattr(
        "openharness.api.provider.detect_provider",
        lambda settings: types.SimpleNamespace(name="anthropic"),
    )
    monkeypatch.setattr("openharness.api.provider.auth_status", lambda settings: "configured")
    monkeypatch.setattr("openharness.plugins.load_plugins", lambda settings, cwd: [])
    monkeypatch.setattr("openharness.skills.load_skill_registry", lambda cwd, settings=None: _FakeSkillRegistry())
    monkeypatch.setattr("openharness.prompts.context.build_runtime_system_prompt", lambda *args, **kwargs: "preview prompt")
    monkeypatch.setattr("openharness.ui.runtime._resolve_api_client_from_settings", lambda settings: object())

    preview = cli._build_dry_run_preview(
        prompt="/plugin list",
        cwd=str(tmp_path),
        model=None,
        max_turns=None,
        base_url=None,
        system_prompt=None,
        append_system_prompt=None,
        api_key=None,
        api_format=None,
        permission_mode=None,
    )

    assert preview["entrypoint"]["kind"] == "slash_command"
    assert preview["entrypoint"]["command"] == "plugin"
    assert preview["entrypoint"]["remote_invocable"] is False
    assert preview["entrypoint"]["remote_admin_opt_in"] is True
    assert preview["entrypoint"]["behavior"] == "stateful"
    assert preview["validation"]["mcp_errors"] == 1
    assert preview["mcp_servers"][0]["status"] == "error"
    assert "command not found in PATH" in preview["mcp_servers"][0]["issues"][0]


def test_build_dry_run_preview_sets_blocked_when_model_prompt_lacks_auth(monkeypatch, tmp_path: Path):
    settings = Settings(api_key="")

    class _FakeSkillRegistry:
        def list_skills(self):
            return []

    monkeypatch.setattr("openharness.config.load_settings", lambda: settings)
    monkeypatch.setattr(
        "openharness.api.provider.detect_provider",
        lambda settings: types.SimpleNamespace(name="anthropic"),
    )
    monkeypatch.setattr("openharness.api.provider.auth_status", lambda settings: "missing")
    monkeypatch.setattr("openharness.plugins.load_plugins", lambda settings, cwd: [])
    monkeypatch.setattr("openharness.skills.load_skill_registry", lambda cwd, settings=None: _FakeSkillRegistry())
    monkeypatch.setattr("openharness.prompts.context.build_runtime_system_prompt", lambda *args, **kwargs: "preview prompt")

    def fake_resolve_api_client(settings):
        raise SystemExit(1)

    monkeypatch.setattr("openharness.ui.runtime._resolve_api_client_from_settings", fake_resolve_api_client)

    preview = cli._build_dry_run_preview(
        prompt="fix the failing tests",
        cwd=str(tmp_path),
        model=None,
        max_turns=None,
        base_url=None,
        system_prompt=None,
        append_system_prompt=None,
        api_key=None,
        api_format=None,
        permission_mode=None,
    )

    assert preview["entrypoint"]["kind"] == "model_prompt"
    assert preview["readiness"]["level"] == "blocked"
    assert any("runtime client" in reason.lower() for reason in preview["readiness"]["reasons"])
    assert any("authentication" in action.lower() or "profile" in action.lower() for action in preview["readiness"]["next_actions"])


def test_build_dry_run_preview_recommends_matching_skills_and_tools(monkeypatch, tmp_path: Path):
    settings = Settings(api_key="sk-test")

    class _FakeSkillRegistry:
        def list_skills(self):
            return [
                types.SimpleNamespace(
                    name="review",
                    description="Review code for bugs and regressions.",
                    content="Use this when reviewing bug fixes and regressions.",
                    source="bundled",
                ),
                types.SimpleNamespace(
                    name="plan",
                    description="Plan implementation work before coding.",
                    content="Use this to design an implementation plan.",
                    source="bundled",
                ),
            ]

    class _FakeToolRegistry:
        def to_api_schema(self):
            return [
                {
                    "name": "grep",
                    "description": "Search code for bug patterns and failing lines.",
                    "input_schema": {"properties": {"pattern": {}, "root": {}}, "required": ["pattern"]},
                },
                {
                    "name": "read_file",
                    "description": "Read files from disk.",
                    "input_schema": {"properties": {"path": {}, "offset": {}}, "required": ["path"]},
                },
            ]

    monkeypatch.setattr("openharness.config.load_settings", lambda: settings)
    monkeypatch.setattr(
        "openharness.api.provider.detect_provider",
        lambda settings: types.SimpleNamespace(name="anthropic"),
    )
    monkeypatch.setattr("openharness.api.provider.auth_status", lambda settings: "configured")
    monkeypatch.setattr("openharness.plugins.load_plugins", lambda settings, cwd: [])
    monkeypatch.setattr("openharness.skills.load_skill_registry", lambda cwd, settings=None: _FakeSkillRegistry())
    monkeypatch.setattr("openharness.tools.create_default_tool_registry", lambda: _FakeToolRegistry())
    monkeypatch.setattr("openharness.prompts.context.build_runtime_system_prompt", lambda *args, **kwargs: "preview prompt")
    monkeypatch.setattr("openharness.ui.runtime._resolve_api_client_from_settings", lambda settings: object())

    preview = cli._build_dry_run_preview(
        prompt="review this bug fix and grep for failing tests",
        cwd=str(tmp_path),
        model=None,
        max_turns=None,
        base_url=None,
        system_prompt=None,
        append_system_prompt=None,
        api_key=None,
        api_format=None,
        permission_mode=None,
    )

    recommended_skills = [entry["name"] for entry in preview["recommendations"]["skills"]]
    recommended_tools = [entry["name"] for entry in preview["recommendations"]["tools"]]

    assert preview["readiness"]["level"] == "ready"
    assert any("you can run this prompt directly" in action.lower() for action in preview["readiness"]["next_actions"])
    assert "review" in recommended_skills
    assert "grep" in recommended_tools


def test_autopilot_run_next_cli(monkeypatch, tmp_path: Path):
    runner = CliRunner()

    class FakeStore:
        def __init__(self, cwd):
            self.cwd = cwd

        async def run_next(self, *, model=None, max_turns=None, permission_mode=None):
            class Result:
                card_id = "ap-1234"
                status = "completed"
                run_report_path = "/tmp/run.md"
                verification_report_path = "/tmp/verify.md"

            return Result()

    monkeypatch.setattr("openharness.autopilot.RepoAutopilotStore", FakeStore)

    result = runner.invoke(app, ["autopilot", "run-next", "--cwd", str(tmp_path)])

    assert result.exit_code == 0
    assert "ap-1234 -> completed" in result.output


def test_autopilot_install_cron_cli(monkeypatch, tmp_path: Path):
    runner = CliRunner()

    class FakeStore:
        def __init__(self, cwd):
            self.cwd = cwd

        def install_default_cron(self):
            return ["autopilot.scan", "autopilot.tick"]

    monkeypatch.setattr("openharness.autopilot.RepoAutopilotStore", FakeStore)

    result = runner.invoke(app, ["autopilot", "install-cron", "--cwd", str(tmp_path)])

    assert result.exit_code == 0
    assert "autopilot.scan" in result.output


def test_autopilot_export_dashboard_cli(monkeypatch, tmp_path: Path):
    runner = CliRunner()

    class FakeStore:
        def __init__(self, cwd):
            self.cwd = cwd

        def export_dashboard(self, output=None):
            return tmp_path / "docs" / "autopilot"

    monkeypatch.setattr("openharness.autopilot.RepoAutopilotStore", FakeStore)

    result = runner.invoke(app, ["autopilot", "export-dashboard", "--cwd", str(tmp_path)])

    assert result.exit_code == 0
    assert "Exported autopilot dashboard" in result.output
