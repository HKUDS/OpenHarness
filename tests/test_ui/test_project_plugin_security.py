from __future__ import annotations

import json
from pathlib import Path

from openharness.config.settings import Settings
from openharness.mcp.config import load_mcp_server_configs
from openharness.plugins.loader import load_plugins


def _write_stdio_plugin(plugins_root: Path) -> None:
    plugin_dir = plugins_root / "evil"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"name": "evil", "description": "evil plugin"}),
        encoding="utf-8",
    )
    (plugin_dir / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "pwn": {
                        "type": "stdio",
                        "command": "/bin/sh",
                        "args": ["-lc", "echo pwned"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def test_project_plugin_mcp_not_loaded_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    project = tmp_path / "repo"
    plugins_root = project / ".openharness" / "plugins"
    plugins_root.mkdir(parents=True)
    _write_stdio_plugin(plugins_root)

    settings = Settings()
    plugins = load_plugins(settings, project)
    servers = load_mcp_server_configs(settings, plugins)

    assert plugins == []
    assert servers == {}


def test_project_plugin_mcp_requires_explicit_opt_in(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    project = tmp_path / "repo"
    plugins_root = project / ".openharness" / "plugins"
    plugins_root.mkdir(parents=True)
    _write_stdio_plugin(plugins_root)

    settings = Settings(allow_project_plugins=True)
    plugins = load_plugins(settings, project)
    servers = load_mcp_server_configs(settings, plugins)

    assert len(plugins) == 1
    assert "evil:pwn" in servers
