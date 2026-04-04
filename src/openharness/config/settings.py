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


class SandboxNetworkSettings(BaseModel):
    """OS-level network restrictions passed to sandbox-runtime."""

    allowed_domains: list[str] = Field(default_factory=list)
    denied_domains: list[str] = Field(default_factory=list)


class SandboxFilesystemSettings(BaseModel):
    """OS-level filesystem restrictions passed to sandbox-runtime."""

    allow_read: list[str] = Field(default_factory=list)
    deny_read: list[str] = Field(default_factory=list)
    allow_write: list[str] = Field(default_factory=lambda: ["."])
    deny_write: list[str] = Field(default_factory=list)


class SandboxSettings(BaseModel):
    """Sandbox-runtime integration settings."""

    enabled: bool = False
    fail_if_unavailable: bool = False
    enabled_platforms: list[str] = Field(default_factory=list)
    network: SandboxNetworkSettings = Field(default_factory=SandboxNetworkSettings)
    filesystem: SandboxFilesystemSettings = Field(default_factory=SandboxFilesystemSettings)


class Settings(BaseModel):
    """Main settings model for OpenHarness."""

    # API configuration
    api_key: str = ""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 16384
    base_url: str | None = None
    api_format: str = "anthropic"  # "anthropic", "openai", or "copilot"
    max_turns: int = 200

    # Behavior
    system_prompt: str | None = None
    permission: PermissionSettings = Field(default_factory=PermissionSettings)
    hooks: dict[str, list[HookDefinition]] = Field(default_factory=dict)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
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
        """Resolve API key with precedence: instance value > env var > empty.

        For ``copilot`` api_format the key is managed separately via
        ``oh auth copilot-login`` and this method is not called.

        Returns the API key string. Raises ValueError if no key is found.
        """
        # Copilot format manages its own auth; skip normal key resolution.
        if self.api_format == "copilot":
            return "copilot-managed"

        if self.api_key:
            return self.api_key

        api_format = (self.api_format or "anthropic").strip().lower()
        if api_format == "openai":
            env_key = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("OPENHARNESS_API_KEY", "")
            if env_key:
                return env_key
            raise ValueError(
                "No API key found. Set OPENAI_API_KEY (or OPENHARNESS_API_KEY) environment "
                "variable, or configure api_key in ~/.openharness/settings.json"
            )

        env_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("OPENHARNESS_API_KEY", "")
        if env_key:
            return env_key

        raise ValueError(
            "No API key found. Set ANTHROPIC_API_KEY (or OPENHARNESS_API_KEY) environment "
            "variable, or configure api_key in ~/.openharness/settings.json"
        )

    def merge_cli_overrides(self, **overrides: Any) -> Settings:
        """Return a new Settings with CLI overrides applied (non-None values only)."""
        updates = {k: v for k, v in overrides.items() if v is not None}
        return self.model_copy(update=updates)


def _apply_env_overrides(settings: Settings) -> Settings:
    """Apply supported environment variable overrides over loaded settings."""
    updates: dict[str, Any] = {}

    api_format = os.environ.get("OPENHARNESS_API_FORMAT")
    if api_format:
        updates["api_format"] = api_format

    # Legacy alias (older builds used --provider / OPENHARNESS_PROVIDER)
    provider = os.environ.get("OPENHARNESS_PROVIDER")
    if provider and "api_format" not in updates:
        updates["api_format"] = provider

    resolved_api_format = (updates.get("api_format") or settings.api_format or "anthropic").strip().lower()

    if resolved_api_format == "openai":
        model = os.environ.get("OPENAI_MODEL") or os.environ.get("OPENHARNESS_MODEL")
        base_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENHARNESS_BASE_URL")
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENHARNESS_API_KEY")
    else:
        model = os.environ.get("ANTHROPIC_MODEL") or os.environ.get("OPENHARNESS_MODEL")
        base_url = os.environ.get("ANTHROPIC_BASE_URL") or os.environ.get("OPENHARNESS_BASE_URL")
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENHARNESS_API_KEY")

    if model:
        updates["model"] = model

    if base_url:
        updates["base_url"] = base_url

    max_tokens = os.environ.get("OPENHARNESS_MAX_TOKENS")
    if max_tokens:
        updates["max_tokens"] = int(max_tokens)

    max_turns = os.environ.get("OPENHARNESS_MAX_TURNS")
    if max_turns:
        updates["max_turns"] = int(max_turns)

    if api_key:
        updates["api_key"] = api_key

    sandbox_enabled = os.environ.get("OPENHARNESS_SANDBOX_ENABLED")
    sandbox_fail = os.environ.get("OPENHARNESS_SANDBOX_FAIL_IF_UNAVAILABLE")
    sandbox_updates: dict[str, Any] = {}
    if sandbox_enabled is not None:
        sandbox_updates["enabled"] = _parse_bool_env(sandbox_enabled)
    if sandbox_fail is not None:
        sandbox_updates["fail_if_unavailable"] = _parse_bool_env(sandbox_fail)
    if sandbox_updates:
        updates["sandbox"] = settings.sandbox.model_copy(update=sandbox_updates)

    if not updates:
        return settings
    return settings.model_copy(update=updates)


def _parse_bool_env(value: str) -> bool:
    """Parse a boolean environment override."""
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
        if isinstance(raw, dict) and "api_format" not in raw and "provider" in raw:
            raw["api_format"] = raw.get("provider")
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
