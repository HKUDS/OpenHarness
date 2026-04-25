"""Plugin runtime types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from openharness.coordinator.agent_definitions import AgentDefinition
from openharness.mcp.types import McpServerConfig
from openharness.plugins.schemas import PluginManifest
from openharness.skills.types import SkillDefinition

if TYPE_CHECKING:
    from openharness.tools.base import BaseTool


@dataclass(frozen=True)
class PluginCommandDefinition:
    """A slash command contributed by a plugin."""

    name: str
    description: str
    content: str
    path: str | None = None
    source: str = "plugin"
    base_dir: str | None = None
    argument_hint: str | None = None
    when_to_use: str | None = None
    version: str | None = None
    model: str | None = None
    effort: str | int | None = None
    disable_model_invocation: bool = False
    user_invocable: bool = True
    is_skill: bool = False
    display_name: str | None = None


@dataclass(frozen=True)
class LoadedPlugin:
    """A loaded plugin and its contributed artifacts."""

    manifest: PluginManifest
    path: Path
    enabled: bool
    skills: list[SkillDefinition] = field(default_factory=list)
    commands: list[PluginCommandDefinition] = field(default_factory=list)
    agents: list[AgentDefinition] = field(default_factory=list)
    tools: list[BaseTool] = field(default_factory=list)
    hooks: dict[str, list] = field(default_factory=dict)
    mcp_servers: dict[str, McpServerConfig] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def description(self) -> str:
        return self.manifest.description
