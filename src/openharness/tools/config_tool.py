"""Tool for reading and updating settings."""

from __future__ import annotations

from typing import Any, get_args, get_origin

from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from pydantic.fields import FieldInfo

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
            target = settings
            *parents, leaf = arguments.key.split(".")
            for part in parents:
                nested = getattr(target, part, None)
                if not isinstance(nested, BaseModel) or part not in type(target).model_fields:
                    return ToolResult(output=f"Unknown config key: {arguments.key}", is_error=True)
                target = nested
            field = type(target).model_fields.get(leaf)
            if field is None:
                return ToolResult(output=f"Unknown config key: {arguments.key}", is_error=True)
            try:
                value = _parse_setting_value(field, arguments.value)
            except ValidationError as exc:
                detail = exc.errors(include_input=False)[0]["msg"]
                return ToolResult(
                    output=f"Invalid value for {arguments.key}: {detail}", is_error=True
                )
            setattr(target, leaf, value)
            save_settings(settings)
            return ToolResult(output=f"Updated {arguments.key}")
        return ToolResult(output="Usage: action=show or action=set with key/value", is_error=True)


def _parse_setting_value(field: FieldInfo, value: str) -> Any:
    adapter = TypeAdapter(field.rebuild_annotation())
    raw = value.strip()
    field_args = get_args(field.annotation)
    if raw == "null" and type(None) in field_args:
        return adapter.validate_python(None)
    try:
        return adapter.validate_python(raw if field.annotation is bool else value)
    except ValidationError:
        if raw.startswith(("[", "{")):
            return adapter.validate_json(raw)
        if any(get_origin(annotation) is list for annotation in (field.annotation, *field_args)):
            return adapter.validate_python([item.strip() for item in raw.split(",") if item.strip()])
        raise
