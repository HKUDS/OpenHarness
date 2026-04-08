"""Tool for reading or activating skills."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from openharness.skills.runtime import activate_skill, build_skill_instruction_message, resolve_skill
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class SkillToolInput(BaseModel):
    """Arguments for skill lookup."""

    name: str = Field(description="Skill name")
    mode: Literal["activate", "read"] = Field(default="activate", description="activate or read")


class SkillTool(BaseTool):
    """Read or activate a loaded skill."""

    name = "skill"
    description = "Activate or read a bundled, user, or plugin skill by name."
    input_model = SkillToolInput

    def is_read_only(self, arguments: SkillToolInput) -> bool:
        return arguments.mode != "activate"

    async def execute(self, arguments: SkillToolInput, context: ToolExecutionContext) -> ToolResult:
        skill = resolve_skill(arguments.name, context.cwd)
        if skill is None:
            return ToolResult(output=f"Skill not found: {arguments.name}", is_error=True)

        if not skill.model_invocable:
            return ToolResult(
                output=f"Skill is not model-invocable: {skill.name}",
                is_error=True,
            )

        if arguments.mode == "read":
            return ToolResult(output=skill.content)

        active_skill = activate_skill(arguments.name, context.cwd)
        if active_skill is None:
            return ToolResult(output=f"Skill not found: {arguments.name}", is_error=True)

        if "query_engine" in context.metadata:
            context.metadata["query_engine"].set_active_skill(active_skill)
        return ToolResult(
            output=build_skill_instruction_message(active_skill.definition),
            metadata={"active_skill": active_skill.definition.name},
        )
