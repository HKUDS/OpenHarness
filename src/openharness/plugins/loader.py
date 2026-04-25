"""Plugin discovery and loading."""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml

from openharness.config.paths import get_config_dir
from openharness.coordinator.agent_definitions import (
    AGENT_COLORS,
    EFFORT_LEVELS,
    ISOLATION_MODES,
    MEMORY_SCOPES,
    PERMISSION_MODES,
    AgentDefinition,
    _parse_agent_frontmatter,
    _parse_positive_int,
    _parse_str_list,
)
from openharness.plugins.schemas import PluginManifest
from openharness.plugins.types import LoadedPlugin, PluginCommandDefinition
from openharness.skills.loader import _parse_skill_markdown
from openharness.skills.types import SkillDefinition

logger = logging.getLogger(__name__)


def get_user_plugins_dir() -> Path:
    """Return the user plugin directory."""
    path = get_config_dir() / "plugins"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_project_plugins_dir(cwd: str | Path) -> Path:
    """Return the project plugin directory."""
    path = Path(cwd).resolve() / ".openharness" / "plugins"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _find_manifest(plugin_dir: Path) -> Path | None:
    """Find plugin.json in standard or .claude-plugin/ locations."""
    for candidate in [
        plugin_dir / "plugin.json",
        plugin_dir / ".claude-plugin" / "plugin.json",
    ]:
        if candidate.exists():
            return candidate
    return None


def discover_plugin_paths(cwd: str | Path, extra_roots: Iterable[str | Path] | None = None) -> list[Path]:
    """Find plugin directories from user and project locations."""
    roots = [get_user_plugins_dir(), get_project_plugins_dir(cwd)]
    if extra_roots:
        for root in extra_roots:
            path = Path(root).expanduser().resolve()
            path.mkdir(parents=True, exist_ok=True)
            roots.append(path)
    paths: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.iterdir()):
            if path.is_dir() and _find_manifest(path) is not None and path not in seen:
                seen.add(path)
                paths.append(path)
    return paths


def discover_plugin_paths_for_settings(
    settings,
    cwd: str | Path,
    extra_roots: Iterable[str | Path] | None = None,
) -> list[Path]:
    """Find plugin directories that are permitted by the active settings."""
    roots = [get_user_plugins_dir()]
    if getattr(settings, "allow_project_plugins", False):
        roots.append(get_project_plugins_dir(cwd))
    if extra_roots:
        for root in extra_roots:
            path = Path(root).expanduser().resolve()
            path.mkdir(parents=True, exist_ok=True)
            roots.append(path)
    paths: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.iterdir()):
            if path.is_dir() and _find_manifest(path) is not None and path not in seen:
                seen.add(path)
                paths.append(path)
    return paths


def load_plugins(settings, cwd: str | Path, extra_roots: Iterable[str | Path] | None = None) -> list[LoadedPlugin]:
    """Load plugins from disk."""
    project_plugins_dir = get_project_plugins_dir(cwd)
    if not getattr(settings, "allow_project_plugins", False) and any(
        path.is_dir() and _find_manifest(path) is not None for path in sorted(project_plugins_dir.iterdir())
    ):
        logger.warning(
            "Found project-local plugins in %s, but they are disabled by default. "
            "Set allow_project_plugins=true if you trust this workspace.",
            project_plugins_dir,
        )
    plugins: list[LoadedPlugin] = []
    for path in discover_plugin_paths_for_settings(settings, cwd, extra_roots=extra_roots):
        plugin = load_plugin(path, settings.enabled_plugins)
        if plugin is not None:
            plugins.append(plugin)
    return plugins


def load_plugin(path: Path, enabled_plugins: dict[str, bool]) -> LoadedPlugin | None:
    """Load one plugin directory."""
    manifest_path = _find_manifest(path)
    if manifest_path is None:
        return None
    try:
        manifest = PluginManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("Failed to load plugin manifest from %s: %s", manifest_path, exc)
        return None
    enabled = enabled_plugins.get(manifest.name, manifest.enabled_by_default)

    skills = _load_plugin_skills(path / manifest.skills_dir)
    commands = _load_plugin_commands(path, manifest)
    agents = _load_plugin_agents(path, manifest)
    tools = _load_plugin_tools(path, manifest) if enabled else []
    hooks = _load_plugin_hooks(path / manifest.hooks_file)
    hooks_dir_file = path / "hooks" / "hooks.json"
    if not hooks and hooks_dir_file.exists():
        hooks = _load_plugin_hooks_structured(hooks_dir_file, path)

    mcp = _load_plugin_mcp(path / manifest.mcp_file)
    mcp_json = path / ".mcp.json"
    if not mcp and mcp_json.exists():
        mcp = _load_plugin_mcp(mcp_json)

    return LoadedPlugin(
        manifest=manifest,
        path=path,
        enabled=enabled,
        skills=skills,
        commands=commands,
        agents=agents,
        hooks=hooks,
        mcp_servers=mcp,
        tools=tools,
    )


def _parse_frontmatter(content: str, path: Path) -> tuple[dict[str, Any], str]:
    if not content.startswith("---\n"):
        return {}, content
    marker = "\n---\n"
    end_index = content.find(marker, 4)
    if end_index == -1:
        return {}, content
    raw_frontmatter = content[4:end_index]
    body = content[end_index + len(marker):]
    try:
        parsed = yaml.safe_load(raw_frontmatter) or {}
    except yaml.YAMLError:
        logger.debug("Failed to parse frontmatter from %s", path, exc_info=True)
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    return parsed, body.strip()


def _extract_description(frontmatter: dict[str, Any], body: str, *, fallback: str) -> str:
    description = frontmatter.get("description")
    if isinstance(description, str) and description.strip():
        return description.strip()
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
        if stripped:
            return stripped
    return fallback


def _walk_plugin_markdown(
    root: Path,
    *,
    stop_at_skill_dir: bool,
) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for current_root, dirnames, filenames in os.walk(root, followlinks=True):
        current = Path(current_root)
        skill_file = current / "SKILL.md"
        if stop_at_skill_dir and skill_file.exists():
            files.append(skill_file)
            dirnames[:] = []
            continue
        for filename in sorted(filenames):
            if filename.lower().endswith(".md"):
                files.append(current / filename)
    return sorted(files)


def _transform_command_files(files: list[Path]) -> list[Path]:
    files_by_dir: dict[Path, list[Path]] = {}
    for file_path in files:
        files_by_dir.setdefault(file_path.parent, []).append(file_path)
    result: list[Path] = []
    for dir_path, dir_files in files_by_dir.items():
        skill_files = [path for path in dir_files if path.name.lower() == "skill.md"]
        if skill_files:
            result.append(skill_files[0])
        else:
            result.extend(sorted(dir_files))
    return sorted(result)


def _command_name_from_file(file_path: Path, base_dir: Path, plugin_name: str) -> str:
    if file_path.name.lower() == "skill.md":
        skill_dir = file_path.parent
        parent_of_skill_dir = skill_dir.parent
        command_base_name = skill_dir.name
        relative_path = parent_of_skill_dir.relative_to(base_dir)
    else:
        command_base_name = file_path.stem
        relative_path = file_path.parent.relative_to(base_dir)
    namespace = ":".join(part for part in relative_path.parts if part and part != ".")
    return (
        f"{plugin_name}:{namespace}:{command_base_name}"
        if namespace
        else f"{plugin_name}:{command_base_name}"
    )


def _load_plugin_skills(path: Path) -> list[SkillDefinition]:
    """Load plugin skills using Claude Code's directory SKILL.md layout."""
    if not path.exists():
        return []
    skills: list[SkillDefinition] = []
    direct_skill = path / "SKILL.md"
    if direct_skill.exists():
        content = direct_skill.read_text(encoding="utf-8")
        name, description = _parse_skill_markdown(path.name, content)
        skills.append(
            SkillDefinition(
                name=name,
                description=description,
                content=content,
                source="plugin",
                path=str(direct_skill),
            )
        )
        return skills
    for child in sorted(path.iterdir()):
        if not child.is_dir():
            continue
        skill_path = child / "SKILL.md"
        if not skill_path.exists():
            continue
        content = skill_path.read_text(encoding="utf-8")
        name, description = _parse_skill_markdown(child.name, content)
        skills.append(
            SkillDefinition(
                name=name,
                description=description,
                content=content,
                source="plugin",
                path=str(skill_path),
            )
        )
    return skills


def _coerce_path_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return []


def _load_plugin_commands(path: Path, manifest: PluginManifest) -> list[PluginCommandDefinition]:
    commands: list[PluginCommandDefinition] = []
    seen: set[Path] = set()
    default_commands_dir = path / "commands"
    commands.extend(
        _load_commands_from_directory(
            default_commands_dir,
            plugin_name=manifest.name,
            seen=seen,
        )
    )

    manifest_commands = manifest.commands
    if isinstance(manifest_commands, dict):
        for command_name, metadata in manifest_commands.items():
            if not isinstance(metadata, dict):
                continue
            source = metadata.get("source")
            content = metadata.get("content")
            if isinstance(source, str):
                command_path = (path / source).resolve()
                if command_path.is_dir():
                    commands.extend(
                        _load_commands_from_directory(
                            command_path,
                            plugin_name=manifest.name,
                            seen=seen,
                        )
                    )
                    continue
                command = _load_single_command_file(
                    command_path,
                    command_name=f"{manifest.name}:{command_name}",
                    metadata_override=metadata,
                    seen=seen,
                )
                if command is not None:
                    commands.append(command)
            elif isinstance(content, str):
                description = str(metadata.get("description") or f"Plugin command from {manifest.name}").strip()
                commands.append(
                    PluginCommandDefinition(
                        name=f"{manifest.name}:{command_name}",
                        description=description,
                        content=content.strip(),
                        source="plugin",
                        argument_hint=metadata.get("argumentHint"),
                        model=metadata.get("model"),
                    )
                )
    else:
        for raw_path in _coerce_path_list(manifest_commands):
            command_path = (path / raw_path).resolve()
            if command_path.is_dir():
                commands.extend(
                    _load_commands_from_directory(
                        command_path,
                        plugin_name=manifest.name,
                        seen=seen,
                    )
                )
            elif command_path.is_file() and command_path.suffix.lower() == ".md":
                command = _load_single_command_file(
                    command_path,
                    command_name=f"{manifest.name}:{command_path.stem}",
                    metadata_override=None,
                    seen=seen,
                )
                if command is not None:
                    commands.append(command)
    return commands


def _load_commands_from_directory(
    directory: Path,
    *,
    plugin_name: str,
    seen: set[Path],
) -> list[PluginCommandDefinition]:
    if not directory.exists():
        return []
    raw_files = _walk_plugin_markdown(directory, stop_at_skill_dir=True)
    files = _transform_command_files(raw_files)
    commands: list[PluginCommandDefinition] = []
    for file_path in files:
        command_name = _command_name_from_file(file_path, directory, plugin_name)
        command = _load_single_command_file(
            file_path,
            command_name=command_name,
            metadata_override=None,
            seen=seen,
        )
        if command is not None:
            if file_path.name.lower() == "skill.md":
                command = PluginCommandDefinition(
                    **{
                        **command.__dict__,
                        "is_skill": True,
                        "base_dir": str(file_path.parent),
                    }
                )
            commands.append(command)
    return commands


def _load_single_command_file(
    file_path: Path,
    *,
    command_name: str,
    metadata_override: dict[str, Any] | None,
    seen: set[Path],
) -> PluginCommandDefinition | None:
    if not file_path.exists():
        return None
    resolved = file_path.resolve()
    if resolved in seen:
        return None
    seen.add(resolved)
    content = file_path.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(content, file_path)
    if metadata_override:
        frontmatter = {
            **frontmatter,
            **{
                "description": metadata_override.get("description", frontmatter.get("description")),
                "argument-hint": metadata_override.get("argumentHint", frontmatter.get("argument-hint")),
                "model": metadata_override.get("model", frontmatter.get("model")),
                "allowed-tools": metadata_override.get("allowedTools", frontmatter.get("allowed-tools")),
            },
        }
    description = _extract_description(frontmatter, body, fallback=f"Plugin command from {command_name}")
    display_name = frontmatter.get("name")
    argument_hint = frontmatter.get("argument-hint")
    when_to_use = frontmatter.get("when_to_use")
    version = frontmatter.get("version")
    model = frontmatter.get("model")
    effort = frontmatter.get("effort")
    disable_model_invocation = bool(frontmatter.get("disable-model-invocation", False))
    user_invocable_raw = frontmatter.get("user-invocable")
    user_invocable = True if user_invocable_raw is None else bool(user_invocable_raw)
    return PluginCommandDefinition(
        name=command_name,
        description=description,
        content=body,
        path=str(file_path),
        source="plugin",
        base_dir=str(file_path.parent),
        argument_hint=str(argument_hint) if isinstance(argument_hint, str) else None,
        when_to_use=str(when_to_use) if isinstance(when_to_use, str) else None,
        version=str(version) if isinstance(version, str) else None,
        model=str(model) if isinstance(model, str) else None,
        effort=effort if isinstance(effort, (str, int)) else None,
        disable_model_invocation=disable_model_invocation,
        user_invocable=user_invocable,
        is_skill=file_path.name.lower() == "skill.md",
        display_name=str(display_name) if isinstance(display_name, str) else None,
    )


def _load_plugin_agents(path: Path, manifest: PluginManifest) -> list[AgentDefinition]:
    agents: list[AgentDefinition] = []
    seen: set[Path] = set()
    default_agents_dir = path / "agents"
    agents.extend(_load_agents_from_directory(default_agents_dir, plugin_name=manifest.name, seen=seen))
    for raw_path in _coerce_path_list(manifest.agents):
        agent_path = (path / raw_path).resolve()
        if agent_path.is_dir():
            agents.extend(_load_agents_from_directory(agent_path, plugin_name=manifest.name, seen=seen))
        elif agent_path.is_file() and agent_path.suffix.lower() == ".md":
            agent = _load_single_agent_file(agent_path, plugin_name=manifest.name, namespace=(), seen=seen)
            if agent is not None:
                agents.append(agent)
    return agents


def _load_agents_from_directory(
    directory: Path,
    *,
    plugin_name: str,
    seen: set[Path],
) -> list[AgentDefinition]:
    if not directory.exists():
        return []
    agents: list[AgentDefinition] = []
    for file_path in _walk_plugin_markdown(directory, stop_at_skill_dir=False):
        namespace = file_path.relative_to(directory).parts[:-1]
        agent = _load_single_agent_file(
            file_path,
            plugin_name=plugin_name,
            namespace=namespace,
            seen=seen,
        )
        if agent is not None:
            agents.append(agent)
    return agents


def _load_single_agent_file(
    file_path: Path,
    *,
    plugin_name: str,
    namespace: tuple[str, ...],
    seen: set[Path],
) -> AgentDefinition | None:
    if not file_path.exists():
        return None
    resolved = file_path.resolve()
    if resolved in seen:
        return None
    seen.add(resolved)
    content = file_path.read_text(encoding="utf-8")
    frontmatter, body = _parse_agent_frontmatter(content)

    base_agent_name = str(frontmatter.get("name", "")).strip() or file_path.stem
    agent_name = ":".join([plugin_name, *namespace, base_agent_name])
    description = str(frontmatter.get("description", "")).strip() or f"Agent from {plugin_name} plugin"
    description = description.replace("\\n", "\n")

    tools = _parse_str_list(frontmatter.get("tools"))
    disallowed_raw = frontmatter.get("disallowedTools", frontmatter.get("disallowed_tools"))
    disallowed_tools = _parse_str_list(disallowed_raw)

    model_raw = frontmatter.get("model")
    model: str | None = None
    if isinstance(model_raw, str) and model_raw.strip():
        trimmed = model_raw.strip()
        model = "inherit" if trimmed.lower() == "inherit" else trimmed

    effort_raw = frontmatter.get("effort")
    effort: str | int | None = None
    if effort_raw is not None:
        if isinstance(effort_raw, int):
            effort = effort_raw if effort_raw > 0 else None
        elif isinstance(effort_raw, str) and effort_raw in EFFORT_LEVELS:
            effort = effort_raw

    background_raw = frontmatter.get("background")
    background = background_raw is True or background_raw == "true"
    skills = _parse_str_list(frontmatter.get("skills")) or []

    color_raw = frontmatter.get("color")
    color = color_raw if isinstance(color_raw, str) and color_raw in AGENT_COLORS else None

    memory_raw = frontmatter.get("memory")
    memory = memory_raw if isinstance(memory_raw, str) and memory_raw in MEMORY_SCOPES else None

    isolation_raw = frontmatter.get("isolation")
    isolation = isolation_raw if isinstance(isolation_raw, str) and isolation_raw in ISOLATION_MODES else None

    max_turns_raw = frontmatter.get("maxTurns", frontmatter.get("max_turns"))
    max_turns = _parse_positive_int(max_turns_raw)

    permission_raw = frontmatter.get("permissionMode", frontmatter.get("permission_mode"))
    permission_mode = (
        permission_raw if isinstance(permission_raw, str) and permission_raw in PERMISSION_MODES else None
    )

    initial_prompt_raw = frontmatter.get("initialPrompt", frontmatter.get("initial_prompt"))
    initial_prompt = initial_prompt_raw.strip() if isinstance(initial_prompt_raw, str) and initial_prompt_raw.strip() else None

    critical_raw = frontmatter.get("criticalSystemReminder", frontmatter.get("critical_system_reminder"))
    critical_system_reminder = critical_raw.strip() if isinstance(critical_raw, str) and critical_raw.strip() else None

    required_mcp_servers = _parse_str_list(
        frontmatter.get("requiredMcpServers", frontmatter.get("required_mcp_servers"))
    )

    permissions: list[str] = []
    raw_permissions = frontmatter.get("permissions", "")
    if raw_permissions:
        permissions = [p.strip() for p in str(raw_permissions).split(",") if p.strip()]

    return AgentDefinition(
        name=agent_name,
        description=description,
        system_prompt=body or None,
        tools=tools,
        disallowed_tools=disallowed_tools,
        model=model,
        effort=effort,
        permission_mode=permission_mode,
        max_turns=max_turns,
        skills=skills,
        mcp_servers=None,
        hooks=None,
        color=color,
        background=background,
        initial_prompt=initial_prompt,
        memory=memory,
        isolation=isolation,
        omit_claude_md=False,
        critical_system_reminder=critical_system_reminder,
        required_mcp_servers=required_mcp_servers,
        permissions=permissions,
        filename=base_agent_name,
        base_dir=str(file_path.parent),
        subagent_type=str(frontmatter.get("subagent_type", agent_name)),
        source="plugin",
    )


def _load_plugin_hooks(path: Path) -> dict[str, list]:
    """Load hooks from a flat hooks.json file."""
    if not path.exists():
        return {}
    from openharness.hooks.schemas import (
        AgentHookDefinition,
        CommandHookDefinition,
        HttpHookDefinition,
        PromptHookDefinition,
    )

    raw = json.loads(path.read_text(encoding="utf-8"))
    parsed: dict[str, list] = {}
    for event, hooks in raw.items():
        parsed[event] = []
        for hook in hooks:
            hook_type = hook.get("type")
            if hook_type == "command":
                parsed[event].append(CommandHookDefinition.model_validate(hook))
            elif hook_type == "prompt":
                parsed[event].append(PromptHookDefinition.model_validate(hook))
            elif hook_type == "http":
                parsed[event].append(HttpHookDefinition.model_validate(hook))
            elif hook_type == "agent":
                parsed[event].append(AgentHookDefinition.model_validate(hook))
    return parsed


def _load_plugin_hooks_structured(path: Path, plugin_root: Path) -> dict[str, list]:
    """Load hooks from structured hooks.json format."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    hooks_data = raw.get("hooks", raw)
    if not isinstance(hooks_data, dict):
        return {}
    parsed: dict[str, list] = {}
    for event, entries in hooks_data.items():
        if not isinstance(entries, list):
            continue
        parsed[event] = []
        for entry in entries:
            hook_list = entry.get("hooks", [])
            matcher = entry.get("matcher", "")
            for hook in hook_list:
                cmd = hook.get("command", "")
                cmd = cmd.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_root))
                parsed[event].append({
                    "type": hook.get("type", "command"),
                    "command": cmd,
                    "matcher": matcher,
                    "timeout": hook.get("timeout"),
                })
    return parsed


def _load_plugin_mcp(path: Path) -> dict[str, object]:
    """Load MCP server configuration from a JSON file."""
    if not path.exists():
        return {}
    from openharness.mcp.types import McpJsonConfig

    raw = json.loads(path.read_text(encoding="utf-8"))
    parsed = McpJsonConfig.model_validate(raw)
    return parsed.mcpServers


def _load_plugin_tools(path: Path, manifest: PluginManifest) -> list:
    """Discover and instantiate BaseTool subclasses from a plugin's tools/ directory."""
    from openharness.tools.base import BaseTool

    tools_dir = path / manifest.tools_dir
    if not tools_dir.is_dir():
        return []

    tools: list[BaseTool] = []
    for py_file in sorted(tools_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        module_name = f"_plugin_tools_{manifest.name}_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception:
            logger.debug("Failed to load plugin tool module %s", py_file, exc_info=True)
            continue

        for attr_name in dir(module):
            attr = getattr(module, attr_name, None)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseTool)
                and attr is not BaseTool
                and hasattr(attr, "name")
                and hasattr(attr, "description")
            ):
                try:
                    instance = attr()
                    tools.append(instance)
                    logger.debug("Loaded plugin tool: %s from %s", instance.name, py_file)
                except Exception:
                    logger.debug("Failed to instantiate tool %s from %s", attr_name, py_file, exc_info=True)
    return tools
