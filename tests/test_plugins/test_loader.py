"""Tests for plugin loading."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from openharness.config.settings import Settings
from openharness.hooks.loader import load_hook_registry
from openharness.plugins import load_plugins
from openharness.plugins.loader import get_user_plugins_dir
from openharness.skills import load_skill_registry


def _write_plugin(root: Path) -> None:
    plugin_dir = root / "example-plugin"
    deploy_dir = plugin_dir / "skills" / "deploy"
    deploy_dir.mkdir(parents=True)
    command_dir = plugin_dir / "commands" / "ops" / "restart"
    command_dir.mkdir(parents=True)
    agents_dir = plugin_dir / "agents" / "review"
    agents_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": "example",
                "version": "1.0.0",
                "description": "Example plugin",
            }
        ),
        encoding="utf-8",
    )
    (deploy_dir / "SKILL.md").write_text(
        "# Deploy\nDeploy with care\n",
        encoding="utf-8",
    )
    (command_dir / "SKILL.md").write_text(
        "---\n"
        "description: Restart services safely\n"
        "---\n\n"
        "# Restart\n\nRun the restart workflow.\n",
        encoding="utf-8",
    )
    (agents_dir / "reviewer.md").write_text(
        "---\n"
        "description: Review code changes\n"
        "---\n\n"
        "# Reviewer\n\nReview the proposed changes.\n",
        encoding="utf-8",
    )
    (plugin_dir / "hooks.json").write_text(
        json.dumps(
            {
                "session_start": [
                    {"type": "command", "command": "printf start"}
                ]
            }
        ),
        encoding="utf-8",
    )
    (plugin_dir / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "demo": {"type": "stdio", "command": "python", "args": ["demo.py"]}
                }
            }
        ),
        encoding="utf-8",
    )


def _write_tool_plugin(root: Path, *, enabled_by_default: bool = True) -> Path:
    plugin_dir = root / "tool-plugin"
    tools_dir = plugin_dir / "tools"
    tools_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": "tool-plugin",
                "version": "1.0.0",
                "description": "Example tool plugin",
                "enabled_by_default": enabled_by_default,
            }
        ),
        encoding="utf-8",
    )
    (tools_dir / "echo_tool.py").write_text(
        "from pydantic import BaseModel\n"
        "from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult\n\n"
        "class EchoArgs(BaseModel):\n"
        "    text: str = 'hello'\n\n"
        "class EchoTool(BaseTool):\n"
        "    name = 'plugin_echo'\n"
        "    description = 'Echo from plugin tool'\n"
        "    input_model = EchoArgs\n\n"
        "    async def execute(self, arguments: EchoArgs, context: ToolExecutionContext) -> ToolResult:\n"
        "        del context\n"
        "        return ToolResult(output=arguments.text)\n",
        encoding="utf-8",
    )
    return plugin_dir


def test_load_plugins_from_project_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    project = tmp_path / "repo"
    plugins_root = project / ".openharness" / "plugins"
    plugins_root.mkdir(parents=True)
    _write_plugin(plugins_root)

    settings = Settings(allow_project_plugins=True)
    plugins = load_plugins(settings, project)

    assert len(plugins) == 1
    plugin = plugins[0]
    assert plugin.manifest.name == "example"
    assert plugin.skills[0].name == "Deploy"
    assert {command.name for command in plugin.commands} == {"example:ops:restart"}
    assert {agent.name for agent in plugin.agents} == {"example:review:reviewer"}
    assert "session_start" in plugin.hooks
    assert "demo" in plugin.mcp_servers


def test_plugin_skills_and_hooks_are_merged(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    project = tmp_path / "repo"
    plugins_root = project / ".openharness" / "plugins"
    plugins_root.mkdir(parents=True)
    _write_plugin(plugins_root)

    settings = Settings(allow_project_plugins=True)
    skills = load_skill_registry(project, settings=settings).list_skills()
    assert any(skill.name == "Deploy" and skill.source == "plugin" for skill in skills)

    plugins = load_plugins(settings, project)
    hooks = load_hook_registry(settings, plugins)
    assert "session_start" in hooks.summary()


def test_project_plugins_are_disabled_by_default(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    project = tmp_path / "repo"
    plugins_root = project / ".openharness" / "plugins"
    plugins_root.mkdir(parents=True)
    _write_plugin(plugins_root)

    plugins = load_plugins(Settings(), project)

    assert plugins == []


def test_project_plugins_disabled_by_default_warns_operator(tmp_path: Path, monkeypatch, caplog):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    project = tmp_path / "repo"
    plugins_root = project / ".openharness" / "plugins"
    plugins_root.mkdir(parents=True)
    _write_plugin(plugins_root)

    with caplog.at_level(logging.WARNING):
        plugins = load_plugins(Settings(), project)

    assert plugins == []
    assert "project-local plugins" in caplog.text
    assert "allow_project_plugins=true" in caplog.text


def test_user_plugins_still_load_when_project_plugins_are_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    project = tmp_path / "repo"
    project_plugins_root = project / ".openharness" / "plugins"
    project_plugins_root.mkdir(parents=True)
    _write_plugin(project_plugins_root)

    user_plugins_root = get_user_plugins_dir()
    _write_plugin(user_plugins_root)

    plugins = load_plugins(Settings(), project)

    assert len(plugins) == 1
    assert plugins[0].manifest.name == "example"


def test_enabled_plugin_tools_are_loaded(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    project = tmp_path / "repo"
    plugins_root = project / ".openharness" / "plugins"
    plugins_root.mkdir(parents=True)
    _write_tool_plugin(plugins_root, enabled_by_default=True)

    plugins = load_plugins(Settings(allow_project_plugins=True), project)

    assert len(plugins) == 1
    plugin = plugins[0]
    assert plugin.enabled is True
    assert [tool.name for tool in plugin.tools] == ["plugin_echo"]


def test_disabled_plugin_tools_are_not_imported(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    project = tmp_path / "repo"
    plugins_root = project / ".openharness" / "plugins"
    plugins_root.mkdir(parents=True)
    plugin_dir = _write_tool_plugin(plugins_root, enabled_by_default=False)
    marker = tmp_path / "tool-imported.txt"
    tool_file = plugin_dir / "tools" / "echo_tool.py"
    tool_file.write_text(
        f"from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('loaded', encoding='utf-8')\n"
        + tool_file.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    plugins = load_plugins(Settings(allow_project_plugins=True), project)

    assert len(plugins) == 1
    plugin = plugins[0]
    assert plugin.enabled is False
    assert plugin.tools == []
    assert not marker.exists()
