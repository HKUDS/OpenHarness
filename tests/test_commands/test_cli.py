"""CLI smoke tests."""

import sys
import types
from pathlib import Path

from typer.testing import CliRunner

import openharness.cli as cli
from openharness.config import load_settings


app = cli.app


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Oh my Harness!" in result.output
    assert "setup" in result.output


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
