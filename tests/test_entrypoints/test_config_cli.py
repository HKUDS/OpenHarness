"""Tests for the top-level config CLI."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from openharness.cli import app
from openharness.config.settings import load_settings


def test_cli_config_set_persists_nested_web_settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    runner = CliRunner()

    mode_result = runner.invoke(app, ["config", "set", "web.resolution_mode", "synthetic_dns"])
    assert mode_result.exit_code == 0
    assert "Updated web.resolution_mode" in mode_result.output

    cidrs_result = runner.invoke(
        app,
        ["config", "set", "web.synthetic_dns_cidrs", "100.64.0.0/10,203.0.113.0/24"],
    )
    assert cidrs_result.exit_code == 0
    assert "Updated web.synthetic_dns_cidrs" in cidrs_result.output

    settings = load_settings()
    assert settings.web.resolution_mode == "synthetic_dns"
    assert settings.web.synthetic_dns_cidrs == ["100.64.0.0/10", "203.0.113.0/24"]
