import asyncio
import json
from pathlib import Path

from openharness.config.settings import load_settings
from openharness.plugins import load_plugins
from openharness.skills import load_skill_registry

from ohmo.runtime import run_ohmo_backend
from ohmo.workspace import get_plugins_dir, get_skills_dir, initialize_workspace


def _write_plugin(root: Path, name: str, skill_name: str) -> None:
    plugin_dir = root / name
    skills_dir = plugin_dir / "skills" / skill_name
    skills_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": name,
                "version": "0.1.0",
                "description": f"{name} plugin",
                "enabled_by_default": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (skills_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {skill_name}\n"
        f"description: Loaded from {name}.\n"
        "---\n\n"
        f"# {skill_name}\n\nLoaded from {name}.\n",
        encoding="utf-8",
    )


def _write_plugin_with_skill_dir(root: Path, name: str, skill_dir_name: str) -> None:
    plugin_dir = root / name
    skill_dir = plugin_dir / "skills" / skill_dir_name
    skill_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": name,
                "version": "0.1.0",
                "description": f"{name} plugin",
                "enabled_by_default": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {skill_dir_name}\n"
        f"description: Loaded from {name}.\n"
        "---\n\n"
        f"# {skill_dir_name}\n",
        encoding="utf-8",
    )


def test_ohmo_loaders_merge_shared_and_private_skills_and_plugins(tmp_path, monkeypatch):
    config_dir = tmp_path / ".openharness"
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(config_dir))
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)

    shared_skills = config_dir / "skills"
    shared_skills.mkdir(parents=True)
    shared_skill_dir = shared_skills / "shared_skill"
    shared_skill_dir.mkdir(parents=True)
    (shared_skill_dir / "SKILL.md").write_text("# shared skill\n\nFrom shared config.\n", encoding="utf-8")
    private_skill_dir = get_skills_dir(workspace) / "private_skill"
    private_skill_dir.mkdir(parents=True)
    (private_skill_dir / "SKILL.md").write_text("# private skill\n\nFrom ohmo workspace.\n", encoding="utf-8")

    shared_plugins = config_dir / "plugins"
    shared_plugins.mkdir(parents=True)
    _write_plugin(shared_plugins, "shared_plugin", "shared_plugin_skill")
    _write_plugin(get_plugins_dir(workspace), "private_plugin", "private_plugin_skill")

    settings = load_settings()
    registry = load_skill_registry(
        tmp_path,
        extra_skill_dirs=[get_skills_dir(workspace)],
        extra_plugin_roots=[get_plugins_dir(workspace)],
        settings=settings,
    )
    names = {skill.name for skill in registry.list_skills()}
    assert "shared skill" in names
    assert "private skill" in names
    assert "shared_plugin_skill" in names
    assert "private_plugin_skill" in names

    plugins = load_plugins(settings, tmp_path, extra_roots=[get_plugins_dir(workspace)])
    plugin_names = {plugin.manifest.name for plugin in plugins}
    assert "shared_plugin" in plugin_names
    assert "private_plugin" in plugin_names


def test_ohmo_private_skill_directory_with_skill_md_is_loaded(tmp_path, monkeypatch):
    config_dir = tmp_path / ".openharness"
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(config_dir))
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)

    skill_dir = get_skills_dir(workspace) / "pikastream-video-meeting"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: pikastream-video-meeting\n"
        "description: Join a meeting via PikaStreaming.\n"
        "---\n\n"
        "# PikaStream Video Meeting\n",
        encoding="utf-8",
    )

    registry = load_skill_registry(
        tmp_path,
        extra_skill_dirs=[get_skills_dir(workspace)],
    )
    skill = registry.get("pikastream-video-meeting")
    assert skill is not None
    assert "PikaStream Video Meeting" in skill.content


def test_run_ohmo_backend_passes_private_skill_and_plugin_roots(tmp_path, monkeypatch):
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)
    captured: dict[str, object] = {}

    async def fake_run_backend_host(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr("ohmo.runtime.run_backend_host", fake_run_backend_host)

    result = asyncio.run(
        run_ohmo_backend(cwd=tmp_path, workspace=workspace, provider_profile="codex")
    )
    assert result == 0
    assert captured["extra_skill_dirs"] == (str(get_skills_dir(workspace)),)
    assert captured["extra_plugin_roots"] == (str(get_plugins_dir(workspace)),)


def test_plugin_loader_supports_directory_skill_layout(tmp_path, monkeypatch):
    config_dir = tmp_path / ".openharness"
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(config_dir))
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)

    _write_plugin_with_skill_dir(get_plugins_dir(workspace), "pika_plugin", "pikastream-video-meeting")

    plugins = load_plugins(load_settings(), tmp_path, extra_roots=[get_plugins_dir(workspace)])
    plugin = next(p for p in plugins if p.manifest.name == "pika_plugin")
    names = {skill.name for skill in plugin.skills}
    assert "pikastream-video-meeting" in names
