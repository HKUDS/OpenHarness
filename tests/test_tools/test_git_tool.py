"""Tests for the structured GitTool."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from openharness.tools import create_default_tool_registry
from openharness.tools.base import ToolExecutionContext
from openharness.tools.git_tool import GitTool, GitToolInput


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Initialise a git repository with one commit."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "README.md").write_text("# Test\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


@pytest.fixture()
def tool() -> GitTool:
    return GitTool()


@pytest.fixture()
def ctx(git_repo: Path) -> ToolExecutionContext:
    return ToolExecutionContext(cwd=git_repo)


# ---------------------------------------------------------------------------
# Read-only operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status(tool: GitTool, ctx: ToolExecutionContext, git_repo: Path):
    result = await tool.execute(
        GitToolInput(operation="status"), ctx
    )
    assert result.is_error is False


@pytest.mark.asyncio
async def test_diff_unstaged(tool: GitTool, ctx: ToolExecutionContext, git_repo: Path):
    (git_repo / "README.md").write_text("# Changed\n", encoding="utf-8")
    result = await tool.execute(
        GitToolInput(operation="diff"), ctx
    )
    assert result.is_error is False
    assert "Changed" in result.output


@pytest.mark.asyncio
async def test_diff_staged(tool: GitTool, ctx: ToolExecutionContext, git_repo: Path):
    (git_repo / "README.md").write_text("# Staged\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=git_repo, check=True, capture_output=True)
    result = await tool.execute(
        GitToolInput(operation="diff", staged=True), ctx
    )
    assert result.is_error is False
    assert "Staged" in result.output


@pytest.mark.asyncio
async def test_log(tool: GitTool, ctx: ToolExecutionContext):
    result = await tool.execute(
        GitToolInput(operation="log"), ctx
    )
    assert result.is_error is False
    assert "initial" in result.output


@pytest.mark.asyncio
async def test_log_max_count(tool: GitTool, ctx: ToolExecutionContext):
    result = await tool.execute(
        GitToolInput(operation="log", max_count=1), ctx
    )
    assert result.is_error is False
    lines = [ln for ln in result.output.splitlines() if ln.strip()]
    assert len(lines) == 1


@pytest.mark.asyncio
async def test_show(tool: GitTool, ctx: ToolExecutionContext):
    result = await tool.execute(
        GitToolInput(operation="show", ref="HEAD"), ctx
    )
    assert result.is_error is False
    assert "initial" in result.output


@pytest.mark.asyncio
async def test_blame(tool: GitTool, ctx: ToolExecutionContext):
    result = await tool.execute(
        GitToolInput(operation="blame", files=["README.md"]), ctx
    )
    assert result.is_error is False
    assert "Test" in result.output  # author name


@pytest.mark.asyncio
async def test_blame_line_range(tool: GitTool, ctx: ToolExecutionContext):
    result = await tool.execute(
        GitToolInput(operation="blame", files=["README.md"], line_start=1, line_end=1),
        ctx,
    )
    assert result.is_error is False


@pytest.mark.asyncio
async def test_branch_list(tool: GitTool, ctx: ToolExecutionContext):
    result = await tool.execute(
        GitToolInput(operation="branch_list"), ctx
    )
    assert result.is_error is False
    # At least the default branch should appear
    assert "main" in result.output or "master" in result.output


# ---------------------------------------------------------------------------
# Mutating operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_and_commit(tool: GitTool, ctx: ToolExecutionContext, git_repo: Path):
    (git_repo / "new.txt").write_text("hello\n", encoding="utf-8")

    add_result = await tool.execute(
        GitToolInput(operation="add", files=["new.txt"]), ctx
    )
    assert add_result.is_error is False

    commit_result = await tool.execute(
        GitToolInput(operation="commit", message="add new file"), ctx
    )
    assert commit_result.is_error is False
    assert "add new file" in commit_result.output or "1 file changed" in commit_result.output


@pytest.mark.asyncio
async def test_branch_create_and_delete(
    tool: GitTool, ctx: ToolExecutionContext
):
    create_result = await tool.execute(
        GitToolInput(operation="branch_create", ref="test-branch"), ctx
    )
    assert create_result.is_error is False

    list_result = await tool.execute(
        GitToolInput(operation="branch_list"), ctx
    )
    assert "test-branch" in list_result.output

    delete_result = await tool.execute(
        GitToolInput(operation="branch_delete", ref="test-branch"), ctx
    )
    assert delete_result.is_error is False


@pytest.mark.asyncio
async def test_checkout(tool: GitTool, ctx: ToolExecutionContext):
    # Create a branch first, then checkout to it
    await tool.execute(
        GitToolInput(operation="branch_create", ref="feature"), ctx
    )
    result = await tool.execute(
        GitToolInput(operation="checkout", ref="feature"), ctx
    )
    assert result.is_error is False

    status = await tool.execute(GitToolInput(operation="branch_list"), ctx)
    assert "* feature" in status.output


@pytest.mark.asyncio
async def test_stash_push_and_pop(
    tool: GitTool, ctx: ToolExecutionContext, git_repo: Path
):
    (git_repo / "README.md").write_text("# Dirty\n", encoding="utf-8")

    push_result = await tool.execute(
        GitToolInput(operation="stash", stash_action="push", stash_message="wip"),
        ctx,
    )
    assert push_result.is_error is False

    # Working tree should be clean after stash
    status = await tool.execute(GitToolInput(operation="status"), ctx)
    assert status.output.strip() == "(no output)" or "README" not in status.output

    pop_result = await tool.execute(
        GitToolInput(operation="stash", stash_action="pop"), ctx
    )
    assert pop_result.is_error is False


@pytest.mark.asyncio
async def test_stash_list(tool: GitTool, ctx: ToolExecutionContext, git_repo: Path):
    (git_repo / "README.md").write_text("# Stashed\n", encoding="utf-8")
    await tool.execute(
        GitToolInput(operation="stash", stash_action="push", stash_message="my stash"),
        ctx,
    )

    result = await tool.execute(
        GitToolInput(operation="stash", stash_action="list"), ctx
    )
    assert result.is_error is False
    assert "my stash" in result.output


@pytest.mark.asyncio
async def test_tag(tool: GitTool, ctx: ToolExecutionContext):
    result = await tool.execute(
        GitToolInput(operation="tag", ref="v1.0.0", message="release 1.0"), ctx
    )
    assert result.is_error is False


@pytest.mark.asyncio
async def test_push_without_remote_fails(tool: GitTool, ctx: ToolExecutionContext):
    result = await tool.execute(
        GitToolInput(operation="push"), ctx
    )
    assert result.is_error is True


# ---------------------------------------------------------------------------
# Validation / safety
# ---------------------------------------------------------------------------


def test_add_rejects_dot():
    with pytest.raises(ValidationError, match="does not allow"):
        GitToolInput(operation="add", files=["."])


def test_add_rejects_dash_A():
    with pytest.raises(ValidationError, match="does not allow"):
        GitToolInput(operation="add", files=["-A"])


def test_add_rejects_all_flag():
    with pytest.raises(ValidationError, match="does not allow"):
        GitToolInput(operation="add", files=["--all"])


@pytest.mark.asyncio
async def test_add_rejects_dash_prefix(
    tool: GitTool, ctx: ToolExecutionContext, git_repo: Path
):
    result = await tool.execute(
        GitToolInput(operation="add", files=["ok.txt", "--force"]), ctx
    )
    assert result.is_error is True
    assert "Invalid file path" in result.output


def test_commit_requires_message():
    with pytest.raises(ValidationError, match="requires 'message'"):
        GitToolInput(operation="commit")


def test_blame_requires_one_file():
    with pytest.raises(ValidationError, match="exactly one file"):
        GitToolInput(operation="blame", files=["a.py", "b.py"])


def test_branch_create_requires_ref():
    with pytest.raises(ValidationError, match="requires 'ref'"):
        GitToolInput(operation="branch_create")


def test_checkout_requires_ref():
    with pytest.raises(ValidationError, match="requires 'ref'"):
        GitToolInput(operation="checkout")


def test_tag_requires_ref_and_message():
    with pytest.raises(ValidationError, match="requires 'ref'"):
        GitToolInput(operation="tag", message="msg")
    with pytest.raises(ValidationError, match="requires 'message'"):
        GitToolInput(operation="tag", ref="v1")


# ---------------------------------------------------------------------------
# Not a git repo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_not_a_git_repo(tool: GitTool, tmp_path: Path):
    ctx = ToolExecutionContext(cwd=tmp_path)
    result = await tool.execute(GitToolInput(operation="status"), ctx)
    assert result.is_error is True
    assert "Not a git repository" in result.output


# ---------------------------------------------------------------------------
# is_read_only
# ---------------------------------------------------------------------------


def test_is_read_only_true_for_read_ops(tool: GitTool):
    for op in ("status", "diff", "log", "show", "blame", "branch_list"):
        # Build minimum valid input for each op
        kwargs: dict = {"operation": op}
        if op == "show":
            kwargs["ref"] = "HEAD"
        if op == "blame":
            kwargs["files"] = ["f.py"]
        args = GitToolInput(**kwargs)
        assert tool.is_read_only(args) is True, f"{op} should be read-only"


def test_is_read_only_false_for_mutating_ops(tool: GitTool):
    for op, kwargs in [
        ("add", {"files": ["f.py"]}),
        ("commit", {"message": "msg"}),
        ("push", {}),
        ("pull", {}),
        ("branch_create", {"ref": "x"}),
        ("branch_delete", {"ref": "x"}),
        ("checkout", {"ref": "x"}),
        ("stash", {}),
        ("tag", {"ref": "v1", "message": "m"}),
    ]:
        args = GitToolInput(operation=op, **kwargs)
        assert tool.is_read_only(args) is False, f"{op} should be mutating"


# ---------------------------------------------------------------------------
# command property (permission integration)
# ---------------------------------------------------------------------------


def test_command_property():
    args = GitToolInput(operation="push", ref="main")
    assert args.command == "git push main"

    args2 = GitToolInput(operation="add", files=["src/a.py", "src/b.py"])
    assert args2.command == "git add src/a.py src/b.py"

    args3 = GitToolInput(operation="branch_create", ref="feat")
    assert args3.command == "git branch create feat"


def test_command_not_in_json_schema():
    schema = GitToolInput.model_json_schema()
    assert "command" not in schema.get("properties", {})


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


def test_registry_includes_git():
    registry = create_default_tool_registry()
    assert registry.get("git") is not None
