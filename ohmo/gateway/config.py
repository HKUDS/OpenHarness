"""Config IO for ohmo gateway."""

from __future__ import annotations

from pathlib import Path

from openharness.config.schema import Config

from ohmo.gateway.models import GatewayConfig
from ohmo.workspace import get_gateway_config_path


def load_gateway_config(workspace: str | Path | None = None) -> GatewayConfig:
    """Load ``.ohmo/gateway.json``."""
    path = get_gateway_config_path(workspace)
    if path.exists():
        return GatewayConfig.model_validate_json(path.read_text(encoding="utf-8"))
    return GatewayConfig()


def save_gateway_config(config: GatewayConfig, workspace: str | Path | None = None) -> Path:
    """Persist ``.ohmo/gateway.json``."""
    path = get_gateway_config_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def build_channel_manager_config(config: GatewayConfig) -> Config:
    """Project gateway settings into the channel compatibility models."""
    root = Config()
    root.channels.send_progress = config.send_progress
    root.channels.send_tool_hints = config.send_tool_hints
    for name in config.enabled_channels:
        if not hasattr(root.channels, name):
            continue
        channel_config = getattr(root.channels, name).model_copy(
            update={"enabled": True, **config.channel_configs.get(name, {})}
        )
        setattr(root.channels, name, channel_config)
    return root
