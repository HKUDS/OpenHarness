"""Workspace-containment regression tests for ``write_file`` / ``edit_file``.

These cover the default (non-Docker-sandbox) configuration.  The shipped
non-interactive runners (task-worker, print mode) install a permission callback
that always approves and supply no ``edit_approval_prompt``, so a prompt-injected
or mistaken model could overwrite or edit host files outside the current
repository by supplying an absolute path or a ``..`` escape.  Mutating file
tools must keep those operations inside the workspace root.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.tools.base import ToolExecutionContext
from openharness.tools.file_edit_tool import FileEditTool, FileEditToolInput
from openharness.tools.file_write_tool import FileWriteTool, FileWriteToolInput


def _workspace(tmp_path: Path) -> Path:
    cwd = tmp_path / "project"
    cwd.mkdir()
    return cwd


# --- write_file (headless / auto-approve path: no edit_approval_prompt) ----


@pytest.mark.asyncio
async def test_write_file_rejects_dotdot_escape_when_autoapproved(tmp_path: Path):
    cwd = _workspace(tmp_path)
    target = tmp_path / "outside-canary.txt"

    # No edit_approval_prompt in metadata == the headless auto-approve path.
    result = await FileWriteTool().execute(
        FileWriteToolInput(path="../outside-canary.txt", content="pwned"),
        ToolExecutionContext(cwd=cwd),
    )

    assert result.is_error is True
    assert "outside the workspace root" in result.output
    assert not target.exists()


@pytest.mark.asyncio
async def test_write_file_rejects_absolute_outside_workspace(tmp_path: Path):
    cwd = _workspace(tmp_path)
    target = tmp_path / "outside-abs.txt"

    result = await FileWriteTool().execute(
        FileWriteToolInput(path=str(target), content="pwned"),
        ToolExecutionContext(cwd=cwd),
    )

    assert result.is_error is True
    assert not target.exists()


@pytest.mark.asyncio
async def test_write_file_rejects_escape_even_with_approval_callback(tmp_path: Path):
    """Containment also holds on the interactive path (approval callback set)."""
    cwd = _workspace(tmp_path)
    target = tmp_path / "outside-interactive.txt"
    approvals: list[str] = []

    async def _approve(path: str, diff: str, added: int, removed: int) -> str:
        approvals.append(path)
        return "once"

    result = await FileWriteTool().execute(
        FileWriteToolInput(path="../outside-interactive.txt", content="pwned"),
        ToolExecutionContext(cwd=cwd, metadata={"edit_approval_prompt": _approve}),
    )

    assert result.is_error is True
    assert "outside the workspace root" in result.output
    assert not target.exists()
    # Containment fails closed before the user is ever prompted.
    assert approvals == []


@pytest.mark.asyncio
async def test_write_file_allows_in_workspace(tmp_path: Path):
    cwd = _workspace(tmp_path)

    result = await FileWriteTool().execute(
        FileWriteToolInput(path="sub/notes.txt", content="hello\n"),
        ToolExecutionContext(cwd=cwd),
    )

    assert result.is_error is False
    assert (cwd / "sub" / "notes.txt").read_text(encoding="utf-8") == "hello\n"


@pytest.mark.asyncio
async def test_write_file_opt_out_allows_outside(tmp_path: Path):
    cwd = _workspace(tmp_path)
    target = tmp_path / "outside-allowed.txt"

    result = await FileWriteTool().execute(
        FileWriteToolInput(path=str(target), content="ok\n"),
        ToolExecutionContext(cwd=cwd, metadata={"restrict_to_workspace": False}),
    )

    assert result.is_error is False
    assert target.read_text(encoding="utf-8") == "ok\n"


@pytest.mark.asyncio
async def test_write_file_allow_paths_permits_extra_root(tmp_path: Path):
    cwd = _workspace(tmp_path)
    shared = tmp_path / "shared"
    shared.mkdir()
    target = shared / "data.txt"

    result = await FileWriteTool().execute(
        FileWriteToolInput(path=str(target), content="shared\n"),
        ToolExecutionContext(cwd=cwd, metadata={"workspace_allow_paths": [str(shared)]}),
    )

    assert result.is_error is False
    assert target.read_text(encoding="utf-8") == "shared\n"


# --- edit_file ------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_file_rejects_dotdot_escape_when_autoapproved(tmp_path: Path):
    cwd = _workspace(tmp_path)
    outside = tmp_path / "outside-edit.txt"
    outside.write_text("keep-me\n", encoding="utf-8")

    result = await FileEditTool().execute(
        FileEditToolInput(path="../outside-edit.txt", old_str="keep-me", new_str="pwned"),
        ToolExecutionContext(cwd=cwd),
    )

    assert result.is_error is True
    assert "outside the workspace root" in result.output
    assert outside.read_text(encoding="utf-8") == "keep-me\n"


@pytest.mark.asyncio
async def test_edit_file_rejects_absolute_outside_workspace(tmp_path: Path):
    cwd = _workspace(tmp_path)
    outside = tmp_path / "outside-edit-abs.txt"
    outside.write_text("keep-me\n", encoding="utf-8")

    result = await FileEditTool().execute(
        FileEditToolInput(path=str(outside), old_str="keep-me", new_str="pwned"),
        ToolExecutionContext(cwd=cwd),
    )

    assert result.is_error is True
    assert outside.read_text(encoding="utf-8") == "keep-me\n"


@pytest.mark.asyncio
async def test_edit_file_allows_in_workspace(tmp_path: Path):
    cwd = _workspace(tmp_path)
    target = cwd / "notes.txt"
    target.write_text("one\ntwo\n", encoding="utf-8")

    result = await FileEditTool().execute(
        FileEditToolInput(path="notes.txt", old_str="two", new_str="TWO"),
        ToolExecutionContext(cwd=cwd),
    )

    assert result.is_error is False
    assert "TWO" in target.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_edit_file_opt_out_allows_outside(tmp_path: Path):
    cwd = _workspace(tmp_path)
    outside = tmp_path / "outside-edit-optout.txt"
    outside.write_text("keep-me\n", encoding="utf-8")

    result = await FileEditTool().execute(
        FileEditToolInput(path=str(outside), old_str="keep-me", new_str="changed"),
        ToolExecutionContext(cwd=cwd, metadata={"restrict_to_workspace": False}),
    )

    assert result.is_error is False
    assert outside.read_text(encoding="utf-8") == "changed\n"
