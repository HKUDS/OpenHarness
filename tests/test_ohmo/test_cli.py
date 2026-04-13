import json
from pathlib import Path

from typer.testing import CliRunner

from ohmo.cli import app


def test_ohmo_help():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "personal-agent app" in result.output
    assert "config" in result.output


def test_ohmo_init_and_doctor(tmp_path: Path):
    runner = CliRunner()
    workspace = tmp_path / ".ohmo-home"
    result = runner.invoke(app, ["init", "--workspace", str(workspace), "--no-interactive"])
    assert result.exit_code == 0
    assert str(workspace) in result.output

    doctor = runner.invoke(app, ["doctor", "--cwd", str(tmp_path), "--workspace", str(workspace)])
    assert doctor.exit_code == 0
    assert "ohmo doctor:" in doctor.output
    assert "workspace: ok" in doctor.output


def test_ohmo_init_existing_workspace_points_to_config(tmp_path: Path):
    runner = CliRunner()
    workspace = tmp_path / ".ohmo-home"
    first = runner.invoke(app, ["init", "--workspace", str(workspace), "--no-interactive"])
    assert first.exit_code == 0

    second = runner.invoke(app, ["init", "--workspace", str(workspace), "--no-interactive"])
    assert second.exit_code == 0
    assert "ohmo workspace already exists." in second.output
    assert "Use `ohmo config`" in second.output


def test_ohmo_init_interactive_writes_gateway_config(tmp_path: Path, monkeypatch):
    runner = CliRunner()
    workspace = tmp_path / ".ohmo-home"
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    user_input = "\n".join(
        [
            "1",  # provider profile
            "y",  # enable telegram
            "*",  # allow_from
            "telegram-token",
            "y",  # reply_to_message
            "n",  # slack
            "n",  # discord
            "n",  # feishu
            "y",  # send_progress
            "y",  # send_tool_hints
            "n",  # allow_remote_admin_commands
        ]
    )
    result = runner.invoke(app, ["init", "--workspace", str(workspace)], input=user_input)
    assert result.exit_code == 0
    config = json.loads((workspace / "gateway.json").read_text(encoding="utf-8"))
    assert config["enabled_channels"] == ["telegram"]
    assert config["channel_configs"]["telegram"]["token"] == "telegram-token"


def test_ohmo_init_interactive_writes_feishu_gateway_config(tmp_path: Path, monkeypatch):
    runner = CliRunner()
    workspace = tmp_path / ".ohmo-home"
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    user_input = "\n".join(
        [
            "1",         # provider profile
            "n",         # telegram
            "n",         # slack
            "n",         # discord
            "y",         # feishu
            "*",         # allow_from
            "cli_app",   # app_id
            "cli_secret",# app_secret
            "enc_key",   # encrypt_key
            "verify_me", # verification_token
            "OK",        # react_emoji
            "y",         # send_progress
            "n",         # send_tool_hints
            "n",         # allow_remote_admin_commands
        ]
    )
    result = runner.invoke(app, ["init", "--workspace", str(workspace)], input=user_input)
    assert result.exit_code == 0
    config = json.loads((workspace / "gateway.json").read_text(encoding="utf-8"))
    assert config["enabled_channels"] == ["feishu"]
    assert config["channel_configs"]["feishu"]["app_id"] == "cli_app"
    assert config["channel_configs"]["feishu"]["app_secret"] == "cli_secret"
    assert config["channel_configs"]["feishu"]["encrypt_key"] == "enc_key"
    assert config["channel_configs"]["feishu"]["verification_token"] == "verify_me"
    assert config["channel_configs"]["feishu"]["react_emoji"] == "OK"


def test_ohmo_config_interactive_can_restart_gateway(tmp_path: Path, monkeypatch):
    runner = CliRunner()
    workspace = tmp_path / ".ohmo-home"
    runner.invoke(app, ["init", "--workspace", str(workspace), "--no-interactive"])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr("ohmo.cli.gateway_status", lambda cwd, workspace: type("State", (), {"running": True})())
    monkeypatch.setattr("ohmo.cli.stop_gateway_process", lambda cwd, workspace: True)
    monkeypatch.setattr("ohmo.cli.start_gateway_process", lambda cwd, workspace: 4321)
    user_input = "\n".join(
        [
            "4",          # provider profile -> codex
            "n",          # telegram
            "n",          # slack
            "n",          # discord
            "y",          # feishu
            "*",          # allow_from
            "cli_app",    # app_id
            "cli_secret", # app_secret
            "",           # encrypt_key
            "verify_me",  # verification_token
            "OK",         # react_emoji
            "y",          # send_progress
            "y",          # send_tool_hints
            "n",          # allow_remote_admin_commands
            "y",          # restart gateway
        ]
    )
    result = runner.invoke(app, ["config", "--workspace", str(workspace)], input=user_input)
    assert result.exit_code == 0
    assert "ohmo gateway restarted (pid=4321)" in result.output
    config = json.loads((workspace / "gateway.json").read_text(encoding="utf-8"))
    assert config["provider_profile"] == "codex"
    assert config["enabled_channels"] == ["feishu"]


def test_ohmo_config_keeps_existing_channel_when_not_reconfigured(tmp_path: Path, monkeypatch):
    runner = CliRunner()
    workspace = tmp_path / ".ohmo-home"
    runner.invoke(app, ["init", "--workspace", str(workspace), "--no-interactive"])
    gateway_path = workspace / "gateway.json"
    config = json.loads(gateway_path.read_text(encoding="utf-8"))
    config["enabled_channels"] = ["feishu"]
    config["channel_configs"]["feishu"] = {
        "allow_from": ["*"],
        "app_id": "old_app",
        "app_secret": "old_secret",
        "encrypt_key": "",
        "verification_token": "old_verify",
        "react_emoji": "OK",
    }
    gateway_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr("ohmo.cli.gateway_status", lambda cwd, workspace: type("State", (), {"running": False})())
    user_input = "\n".join(
        [
            "4",  # provider profile -> codex
            "n",  # telegram
            "n",  # slack
            "n",  # discord
            "n",  # reconfigure feishu? keep existing
            "y",  # send_progress
            "y",  # send_tool_hints
            "n",  # allow_remote_admin_commands
        ]
    )
    result = runner.invoke(app, ["config", "--workspace", str(workspace)], input=user_input)
    assert result.exit_code == 0
    updated = json.loads(gateway_path.read_text(encoding="utf-8"))
    assert updated["enabled_channels"] == ["feishu"]
    assert updated["channel_configs"]["feishu"]["app_id"] == "old_app"
    assert updated["channel_configs"]["feishu"]["app_secret"] == "old_secret"
