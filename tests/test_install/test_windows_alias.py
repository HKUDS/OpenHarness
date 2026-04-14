"""Installer regressions for Windows command aliases."""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib


def test_pyproject_exposes_openh_console_script():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    scripts = data["project"]["scripts"]
    assert scripts["openh"] == "openharness.cli:app"
    assert scripts["oh"] == "openharness.cli:app"


def test_powershell_installer_recommends_openh_for_windows():
    script = Path("scripts/install.ps1").read_text(encoding="utf-8")
    assert "openh.exe" in script
    assert "Launch (PowerShell):     openh" in script
    assert "Out-Host" in script
