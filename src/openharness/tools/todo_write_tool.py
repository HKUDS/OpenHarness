"""Tool for maintaining a project TODO file."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class TodoWriteToolInput(BaseModel):
    """Arguments for TODO writes."""

    item: str = Field(description="TODO item text")
    checked: bool = Field(default=False)
    path: str = Field(default="TODO.md")


class TodoWriteTool(BaseTool):
    """Add or update an item in a TODO markdown file."""

    name = "todo_write"
    description = "Add a new TODO item or mark an existing one as done in a markdown checklist file."
    input_model = TodoWriteToolInput

    async def execute(self, arguments: TodoWriteToolInput, context: ToolExecutionContext) -> ToolResult:
        path = Path(context.cwd) / arguments.path
        existing = path.read_text(encoding="utf-8") if path.exists() else "# TODO\n"

        unchecked_line = f"- [ ] {arguments.item}"
        checked_line = f"- [x] {arguments.item}"
        target_line = checked_line if arguments.checked else unchecked_line

        if unchecked_line in existing and arguments.checked:
            # Mark existing unchecked item as done (in-place update)
            updated = existing.replace(unchecked_line, checked_line, 1)
        elif target_line in existing:
            # Item already in desired state — no-op
            return ToolResult(output=f"No change needed in {path}")
        else:
            # New item — append
            updated = existing.rstrip() + f"\n{target_line}\n"

        path.write_text(updated, encoding="utf-8")
        return ToolResult(output=f"Updated {path}")
