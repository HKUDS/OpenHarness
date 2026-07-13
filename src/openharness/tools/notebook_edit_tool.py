"""Minimal Jupyter notebook editing tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class NotebookEditToolInput(BaseModel):
    """Arguments for notebook editing."""

    path: str = Field(description="Path to the .ipynb file")
    cell_index: int = Field(description="Zero-based cell index", ge=0)
    new_source: str = Field(description="Replacement or appended source for the target cell")
    cell_type: Literal["code", "markdown"] = Field(default="code")
    mode: Literal["replace", "append"] = Field(default="replace")
    create_if_missing: bool = Field(default=True)


class NotebookEditTool(BaseTool):
    """Edit notebook cells without requiring nbformat."""

    name = "notebook_edit"
    description = "Create or edit a Jupyter notebook cell."
    input_model = NotebookEditToolInput

    async def execute(
        self,
        arguments: NotebookEditToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        path = _resolve_path(context.cwd, arguments.path)
        cwd_resolved = context.cwd.resolve()
        try:
            path.relative_to(cwd_resolved)
        except ValueError:
            return ToolResult(
                output=f"Access denied: {path} is outside the workspace root ({cwd_resolved}).",
                is_error=True,
            )
        notebook = _load_notebook(path, create_if_missing=arguments.create_if_missing)
        if notebook is None:
            return ToolResult(output=f"Notebook not found: {path}", is_error=True)

        cells = notebook.setdefault("cells", [])
        while len(cells) <= arguments.cell_index:
            cells.append(_empty_cell(arguments.cell_type))

        cell = cells[arguments.cell_index]
        cell["cell_type"] = arguments.cell_type
        cell.setdefault("metadata", {})
        if arguments.cell_type == "code":
            cell.setdefault("outputs", [])
            cell.setdefault("execution_count", None)

        existing = _normalize_source(cell.get("source", ""))
        updated = arguments.new_source if arguments.mode == "replace" else f"{existing}{arguments.new_source}"
        cell["source"] = updated

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(notebook, indent=2) + "\n", encoding="utf-8")
        return ToolResult(output=f"Updated notebook cell {arguments.cell_index} in {path}")


def _resolve_path(base: Path, candidate: str) -> Path:
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _load_notebook(path: Path, *, create_if_missing: bool) -> dict | None:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not create_if_missing:
        return None
    return {
        "cells": [],
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _empty_cell(cell_type: str) -> dict:
    if cell_type == "markdown":
        return {"cell_type": "markdown", "metadata": {}, "source": ""}
    return {
        "cell_type": "code",
        "metadata": {},
        "source": "",
        "outputs": [],
        "execution_count": None,
    }


def _normalize_source(source: str | list[str]) -> str:
    if isinstance(source, list):
        return "".join(source)
    return str(source)
