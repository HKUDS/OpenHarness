"""Workspace-containment regression tests for ``read_file``.

These cover the default (non-Docker-sandbox) configuration, where model- or
LLM-supplied paths must stay inside the workspace root.  Without containment a
prompt-injected or mistaken model can read host files outside the current
repository by supplying an absolute path or a ``..`` escape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.tools.base import ToolExecutionContext
from openharness.tools.file_read_tool import FileReadTool, FileReadToolInput


def _workspace(tmp_path: Path) -> Path:
    cwd = tmp_path / "project"
    cwd.mkdir()
    return cwd


@pytest.mark.asyncio
async def test_read_file_rejects_absolute_outside_workspace(tmp_path: Path):
    cwd = _workspace(tmp_path)
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("super-secret\n", encoding="utf-8")

    result = await FileReadTool().execute(
        FileReadToolInput(path=str(outside)),
        ToolExecutionContext(cwd=cwd),
    )

    assert result.is_error is True
    assert "super-secret" not in result.output
    assert "outside the workspace root" in result.output


@pytest.mark.asyncio
async def test_read_file_rejects_dotdot_escape(tmp_path: Path):
    cwd = _workspace(tmp_path)
    (tmp_path / "outside-secret.txt").write_text("super-secret\n", encoding="utf-8")

    result = await FileReadTool().execute(
        FileReadToolInput(path="../outside-secret.txt"),
        ToolExecutionContext(cwd=cwd),
    )

    assert result.is_error is True
    assert "super-secret" not in result.output
    assert "outside the workspace root" in result.output


@pytest.mark.asyncio
async def test_read_file_allows_in_workspace(tmp_path: Path):
    cwd = _workspace(tmp_path)
    (cwd / "notes.txt").write_text("alpha\nbeta\n", encoding="utf-8")

    result = await FileReadTool().execute(
        FileReadToolInput(path="notes.txt"),
        ToolExecutionContext(cwd=cwd),
    )

    assert result.is_error is False
    assert "alpha" in result.output


@pytest.mark.asyncio
async def test_read_file_opt_out_allows_outside(tmp_path: Path):
    cwd = _workspace(tmp_path)
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("super-secret\n", encoding="utf-8")

    result = await FileReadTool().execute(
        FileReadToolInput(path=str(outside)),
        ToolExecutionContext(cwd=cwd, metadata={"restrict_to_workspace": False}),
    )

    assert result.is_error is False
    assert "super-secret" in result.output


@pytest.mark.asyncio
async def test_read_file_allow_paths_permits_extra_root(tmp_path: Path):
    cwd = _workspace(tmp_path)
    shared = tmp_path / "shared"
    shared.mkdir()
    target = shared / "data.txt"
    target.write_text("shared-data\n", encoding="utf-8")

    result = await FileReadTool().execute(
        FileReadToolInput(path=str(target)),
        ToolExecutionContext(
            cwd=cwd,
            metadata={"workspace_allow_paths": [str(shared)]},
        ),
    )

    assert result.is_error is False
    assert "shared-data" in result.output
