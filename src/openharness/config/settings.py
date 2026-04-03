"""Settings model and loading logic for OpenHarness.

Settings are resolved with the following precedence (highest first):
1. CLI arguments
2. Environment variables (ANTHROPIC_API_KEY, OPENHARNESS_MODEL, etc.)
3. Config file (~/.openharness/settings.json)
4. Defaults
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from openharness.hooks.schemas import HookDefinition
from openharness.mcp.types import McpServerConfig
from openharness.permissions.modes import PermissionMode


class PathRuleConfig(BaseModel):
    """A glob-pattern path permission rule."""

    pattern: str
    allow: bool = True


class PermissionSettings(BaseModel):
    """Permission mode configuration."""

    mode: PermissionMode = PermissionMode.DEFAULT
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    path_rules: list[PathRuleConfig] = Field(default_factory=list)
    denied_commands: list[str] = Field(default_factory=list)


class MemorySettings(BaseModel):
    """Memory system configuration."""

    enabled: bool = True
    max_files: int = 5
    max_entrypoint_lines: int = 200


class Settings(BaseModel):
    """Main settings model for OpenHarness."""

    # API configuration
    api_key: str = ""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 16384
    base_url: str | None = None

    # Vertex AI / Google Cloud configuration (used when model is a Gemini variant)
    vertex_project: str | None = None
    vertex_location: str | None = None

    # Behavior
    system_prompt: str | None = None
    permission: PermissionSettings = Field(default_factory=PermissionSettings)
    hooks: dict[str, list[HookDefinition]] = Field(default_factory=dict)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    enabled_plugins: dict[str, bool] = Field(default_factory=dict)
    mcp_servers: dict[str, McpServerConfig] = Field(default_factory=dict)

    # UI
    theme: str = "default"
    output_style: str = "default"
    vim_mode: bool = False
    voice_mode: bool = False
    fast_mode: bool = False
    effort: str = "medium"
    passes: int = 1
    verbose: bool = False

    def resolve_api_key(self) -> str:
        """Resolve the API key appropriate for the configured model.

        Precedence (highest first):
        1. ``api_key`` field set directly on this instance or via ``OPENHARNESS_API_KEY``
        2. Provider-specific environment variable (``GEMINI_API_KEY`` / ``VERTEX_AI_API_KEY``
           for Gemini models; ``ANTHROPIC_API_KEY`` for all others)

        Raises ``ValueError`` when no key can be resolved.
        """
        if self.api_key:
            return self.api_key

        if "gemini" in self.model.lower():
            env_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("VERTEX_AI_API_KEY", "")
            if env_key:
                return env_key
            raise ValueError(
                "No API key found for Gemini model. "
                "Set GEMINI_API_KEY or VERTEX_AI_API_KEY, "
                "or configure api_key in ~/.openharness/settings.json"
            )

        env_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if env_key:
            return env_key

        raise ValueError(
            "No API key found. Set ANTHROPIC_API_KEY environment variable "
            "or configure api_key in ~/.openharness/settings.json"
        )

    def merge_cli_overrides(self, **overrides: Any) -> Settings:
        """Return a new Settings with CLI overrides applied (non-None values only)."""
        updates = {k: v for k, v in overrides.items() if v is not None}
        return self.model_copy(update=updates)


def _apply_env_overrides(settings: Settings) -> Settings:
    """Apply supported environment variable overrides over loaded settings.

    Note: provider-specific API keys (``ANTHROPIC_API_KEY``, ``GEMINI_API_KEY``,
    ``VERTEX_AI_API_KEY``) are intentionally **not** loaded into the ``api_key``
    field here.  They are resolved lazily and model-aware by ``resolve_api_key()``.
    Use ``OPENHARNESS_API_KEY`` only if you need to pin an explicit key regardless
    of the model.
    """
    updates: dict[str, Any] = {}

    model = os.environ.get("ANTHROPIC_MODEL") or os.environ.get("OPENHARNESS_MODEL")
    if model:
        updates["model"] = model

    base_url = os.environ.get("ANTHROPIC_BASE_URL") or os.environ.get("OPENHARNESS_BASE_URL")
    if base_url:
        updates["base_url"] = base_url

    max_tokens = os.environ.get("OPENHARNESS_MAX_TOKENS")
    if max_tokens:
        updates["max_tokens"] = int(max_tokens)

    # Explicit key override — use this only to pin a key unconditionally.
    # Model-specific keys (ANTHROPIC_API_KEY, GEMINI_API_KEY, etc.) are
    # resolved lazily by Settings.resolve_api_key() so they never clobber
    # each other when switching providers.
    api_key = os.environ.get("OPENHARNESS_API_KEY")
    if api_key:
        updates["api_key"] = api_key

    vertex_project = os.environ.get("VERTEX_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if vertex_project:
        updates["vertex_project"] = vertex_project

    vertex_location = os.environ.get("VERTEX_LOCATION") or os.environ.get("GOOGLE_CLOUD_LOCATION")
    if vertex_location:
        updates["vertex_location"] = vertex_location

    if not updates:
        return settings
    return settings.model_copy(update=updates)


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from config file, merging with defaults.

    Args:
        config_path: Path to settings.json. If None, uses the default location.

    Returns:
        Settings instance with file values merged over defaults.
    """
    if config_path is None:
        from openharness.config.paths import get_config_file_path

        config_path = get_config_file_path()

    if config_path.exists():
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        return _apply_env_overrides(Settings.model_validate(raw))

    return _apply_env_overrides(Settings())


def save_settings(settings: Settings, config_path: Path | None = None) -> None:
    """Persist settings to the config file.

    Args:
        settings: Settings instance to save.
        config_path: Path to write. If None, uses the default location.
    """
    if config_path is None:
        from openharness.config.paths import get_config_file_path

        config_path = get_config_file_path()

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        settings.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
