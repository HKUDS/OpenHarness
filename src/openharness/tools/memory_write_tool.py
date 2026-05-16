"""Tool for writing durable OpenHarness memory entries."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from openharness.memory.manager import remove_memory_entry, upsert_memory_entry
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class MemoryWriteToolInput(BaseModel):
    """Arguments for durable memory writes."""

    action: Literal["upsert", "delete"] = Field(
        default="upsert",
        description="Whether to create/update a durable memory entry or delete one by key.",
    )
    key: str = Field(description="Stable key used to deduplicate durable memory entries.")
    title: str = Field(default="", description="Short human-readable title for the memory entry.")
    content: str = Field(default="", description="Markdown body for the durable memory entry.")
    description: str = Field(default="", description="One-line summary used for indexing and retrieval.")
    memory_type: str = Field(default="", description="Durable memory category such as preference, project, or environment.")

    @model_validator(mode="after")
    def _validate_required_fields(self) -> "MemoryWriteToolInput":
        if self.action == "upsert":
            if not self.title.strip():
                raise ValueError("title is required when action=upsert")
            if not self.content.strip():
                raise ValueError("content is required when action=upsert")
        return self


class MemoryWriteTool(BaseTool):
    """Create, update, or delete durable memory in the OpenHarness memory store."""

    name = "memory_write"
    description = (
        "Create, update, or delete durable memory entries stored in OpenHarness's internal project memory directory. "
        "Use it only for information that should persist across future sessions."
    )
    input_model = MemoryWriteToolInput

    def is_read_only(self, arguments: MemoryWriteToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: MemoryWriteToolInput, context: ToolExecutionContext) -> ToolResult:
        if arguments.action == "delete":
            removed = remove_memory_entry(context.cwd, arguments.key)
            if removed:
                return ToolResult(
                    output=f"Deleted memory entry {arguments.key}",
                    metadata={"key": arguments.key, "action": "delete", "deleted": True},
                )
            return ToolResult(
                output=f"Memory entry not found for {arguments.key}",
                metadata={"key": arguments.key, "action": "delete", "deleted": False},
            )

        path, status = upsert_memory_entry(
            context.cwd,
            key=arguments.key,
            title=arguments.title,
            content=arguments.content,
            description=arguments.description,
            memory_type=arguments.memory_type,
        )
        return ToolResult(
            output=f"{status.capitalize()} durable memory {path.name}",
            metadata={
                "key": arguments.key,
                "action": arguments.action,
                "status": status,
                "memory_path": str(path),
            },
        )