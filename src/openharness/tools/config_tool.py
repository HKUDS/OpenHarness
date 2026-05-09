"""Tool for reading and updating settings."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from openharness.config.settings import load_settings, save_settings
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class ConfigToolInput(BaseModel):
    """Arguments for config access."""

    action: str = Field(default="show", description="show or set")
    key: str | None = Field(default=None)
    value: str | None = Field(default=None)


class ConfigTool(BaseTool):
    """Read or update OpenHarness settings."""

    name = "config"
    description = "Read or update OpenHarness settings."
    input_model = ConfigToolInput

    async def execute(self, arguments: ConfigToolInput, context: ToolExecutionContext) -> ToolResult:
        del context
        settings = load_settings()
        if arguments.action == "show":
            return ToolResult(output=settings.model_dump_json(indent=2))
        if arguments.action == "set" and arguments.key and arguments.value is not None:
            target: Any = settings
            parts = arguments.key.split(".")
            for part in parts[:-1]:
                if not hasattr(target, part):
                    return ToolResult(output=f"Unknown config key: {arguments.key}", is_error=True)
                target = getattr(target, part)
            leaf = parts[-1]
            if not hasattr(target, leaf):
                return ToolResult(output=f"Unknown config key: {arguments.key}", is_error=True)
            current = getattr(target, leaf)
            value: Any = arguments.value
            if isinstance(current, bool):
                value = arguments.value.strip().lower() in {"1", "true", "yes", "on"}
            elif isinstance(current, int) and not isinstance(current, bool):
                value = int(arguments.value)
            elif isinstance(current, float):
                value = float(arguments.value)
            setattr(target, leaf, value)
            save_settings(settings)
            return ToolResult(output=f"Updated {arguments.key}")
        return ToolResult(output="Usage: action=show or action=set with key/value", is_error=True)
