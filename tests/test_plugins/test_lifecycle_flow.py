"""Real plugin lifecycle integration tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from openharness.config.settings import Settings, load_settings
from openharness.mcp.client import McpClientManager
from openharness.mcp.config import load_mcp_server_configs
from openharness.plugins import load_plugins
from openharness.plugins.installer import install_plugin_from_path, uninstall_plugin
from openharness.tools import create_default_tool_registry
from openharness.tools.base import ToolExecutionContext


def _write_plugin(source_root: Path, server_script: Path) -> Path:
    plugin_dir = source_root / "fixture-plugin"
    fixture_skill_dir = plugin_dir / "skills" / "fixture"
    fixture_skill_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": "fixture-plugin",
                "version": "1.0.0",
                "description": "Fixture plugin",
            }
        ),
        encoding="utf-8",
    )
    (fixture_skill_dir / "SKILL.md").write_text(
        "# FixtureSkill\nFixture skill content for plugin flow.\n",
        encoding="utf-8",
    )
    (plugin_dir / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "fixture": {
                        "type": "stdio",
                        "command": sys.executable,
                        "args": [str(server_script)],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return plugin_dir


@pytest.mark.asyncio
async def test_plugin_install_load_and_uninstall_flow(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    project = tmp_path / "project"
    project.mkdir()
    server_script = Path(__file__).resolve().parents[1] / "fixtures" / "fake_mcp_server.py"
    plugin_source = _write_plugin(tmp_path / "source", server_script)

    installed_path = install_plugin_from_path(plugin_source)
    assert installed_path.exists()

    settings = Settings()
    plugins = load_plugins(settings, project)
    assert len(plugins) == 1
    assert plugins[0].manifest.name == "fixture-plugin"
    assert plugins[0].skills[0].name == "FixtureSkill"

    manager = McpClientManager(load_mcp_server_configs(settings, plugins))
    await manager.connect_all()
    try:
        registry = create_default_tool_registry(manager)
        skill_tool = registry.get("skill")
        skill_result = await skill_tool.execute(
            skill_tool.input_model.model_validate({"name": "FixtureSkill"}),
            ToolExecutionContext(cwd=project),
        )
        assert "Fixture skill content" in skill_result.output

        mcp_tool = registry.get("mcp__fixture-plugin_fixture__hello")
        assert mcp_tool is not None
        mcp_result = await mcp_tool.execute(
            mcp_tool.input_model.model_validate({"name": "plugin"}),
            ToolExecutionContext(cwd=project),
        )
        assert mcp_result.output == "fixture-hello:plugin"
    finally:
        await manager.close()

    assert uninstall_plugin("fixture-plugin") is True
    assert load_plugins(load_settings(), project) == []


def test_uninstall_plugin_rejects_traversal_name_without_deleting_sibling(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "marker.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid plugin name"):
        uninstall_plugin("../../victim")

    assert victim.exists()
    assert (victim / "marker.txt").read_text(encoding="utf-8") == "keep"
