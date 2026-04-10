"""Structured git operations tool with built-in safety constraints."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

_READ_ONLY_OPS = frozenset({"status", "diff", "log", "show", "blame", "branch_list"})

_REJECTED_ADD_ENTRIES = frozenset({".", "-A", "--all", "-a", "*"})

_OUTPUT_LIMIT = 12000


async def _run_git(*args: str, cwd: Path) -> tuple[int, str, str]:
    """Run a git command, returning (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": ""},
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    return (
        proc.returncode or 0,
        stdout_bytes.decode(errors="replace").strip(),
        stderr_bytes.decode(errors="replace").strip(),
    )


def _to_result(rc: int, stdout: str, stderr: str) -> ToolResult:
    """Convert git subprocess output to a ToolResult."""
    output = stdout or stderr or "(no output)"
    if len(output) > _OUTPUT_LIMIT:
        output = f"{output[:_OUTPUT_LIMIT]}\n...[truncated]..."
    return ToolResult(output=output, is_error=rc != 0)


class GitToolInput(BaseModel):
    """Arguments for structured git operations."""

    operation: Literal[
        "status",
        "diff",
        "log",
        "show",
        "blame",
        "branch_list",
        "add",
        "commit",
        "push",
        "pull",
        "branch_create",
        "branch_delete",
        "checkout",
        "stash",
        "tag",
    ] = Field(description="The git operation to perform")

    files: list[str] | None = Field(
        default=None,
        description="Explicit list of file paths. Required for 'add' (no wildcards or '.').",
    )
    message: str | None = Field(
        default=None,
        description="Commit or tag message. Required for 'commit' and 'tag'.",
    )
    ref: str | None = Field(
        default=None,
        description="Branch name, commit SHA, or ref for operations that target a specific revision.",
    )
    max_count: int = Field(
        default=20, ge=1, le=200, description="Maximum number of log entries to return."
    )
    oneline: bool = Field(default=True, description="Use --oneline format for log.")
    staged: bool = Field(default=False, description="Show staged changes (--cached) for diff.")
    line_start: int | None = Field(default=None, ge=1, description="Start line for blame range.")
    line_end: int | None = Field(default=None, ge=1, description="End line for blame range.")
    stash_action: Literal["push", "pop", "list", "drop"] = Field(
        default="push", description="Stash sub-action."
    )
    stash_message: str | None = Field(
        default=None, description="Optional message for stash push."
    )
    remote: str = Field(default="origin", description="Remote name for push/pull.")
    start_point: str | None = Field(
        default=None,
        description="Starting point (commit/branch) for branch_create. Defaults to HEAD.",
    )

    @model_validator(mode="after")
    def validate_operation_fields(self) -> "GitToolInput":
        op = self.operation

        if op == "add":
            if not self.files:
                raise ValueError("'add' requires a non-empty 'files' list")
            for f in self.files:
                if f in _REJECTED_ADD_ENTRIES:
                    raise ValueError(
                        f"'add' does not allow '{f}'. Specify individual file paths."
                    )

        if op == "commit" and not self.message:
            raise ValueError("'commit' requires 'message'")

        if op == "blame":
            if not self.files or len(self.files) != 1:
                raise ValueError("'blame' requires exactly one file in 'files'")

        if op == "show" and not self.ref and not self.files:
            raise ValueError("'show' requires 'ref' (commit/object) or 'files'")

        if op == "tag":
            if not self.ref:
                raise ValueError("'tag' requires 'ref' (the tag name)")
            if not self.message:
                raise ValueError("'tag' requires 'message'")

        if op == "branch_create" and not self.ref:
            raise ValueError("'branch_create' requires 'ref' (the new branch name)")

        if op == "branch_delete" and not self.ref:
            raise ValueError("'branch_delete' requires 'ref' (the branch to delete)")

        if op == "checkout" and not self.ref:
            raise ValueError("'checkout' requires 'ref' (branch or commit to check out)")

        return self

    @property
    def command(self) -> str:
        """Synthesize a git command string for permission system pattern matching."""
        parts = ["git", self.operation.replace("_", " ")]
        if self.ref:
            parts.append(self.ref)
        if self.files:
            parts.extend(self.files)
        return " ".join(parts)


class GitTool(BaseTool):
    """Perform structured git operations with built-in safety constraints.

    Safety by design: dangerous operations like force push, hard reset,
    clean, --no-verify, and ``git add .`` cannot be expressed in the schema.
    """

    name = "git"
    description = (
        "Perform structured git operations with built-in safety constraints. "
        "Supports: status, diff, log, show, blame, branch_list, add, commit, "
        "push, pull, branch_create, branch_delete, checkout, stash, tag."
    )
    input_model = GitToolInput

    def is_read_only(self, arguments: GitToolInput) -> bool:
        return arguments.operation in _READ_ONLY_OPS

    async def execute(
        self, arguments: GitToolInput, context: ToolExecutionContext
    ) -> ToolResult:
        cwd = context.cwd

        # Verify we are inside a git repository.
        rc, _, _ = await _run_git("rev-parse", "--git-dir", cwd=cwd)
        if rc != 0:
            return ToolResult(output="Not a git repository", is_error=True)

        handler = _DISPATCH.get(arguments.operation)
        if handler is None:
            return ToolResult(
                output=f"Unknown operation: {arguments.operation}", is_error=True
            )

        return await handler(arguments, cwd)


# ---------------------------------------------------------------------------
# Operation handlers
# ---------------------------------------------------------------------------


async def _handle_status(args: GitToolInput, cwd: Path) -> ToolResult:
    cmd = ["status", "--short"]
    if args.files:
        cmd.append("--")
        cmd.extend(args.files)
    rc, stdout, stderr = await _run_git(*cmd, cwd=cwd)
    return _to_result(rc, stdout, stderr)


async def _handle_diff(args: GitToolInput, cwd: Path) -> ToolResult:
    cmd: list[str] = ["diff"]
    if args.staged:
        cmd.append("--cached")
    if args.ref:
        cmd.append(args.ref)
    if args.files:
        cmd.append("--")
        cmd.extend(args.files)
    rc, stdout, stderr = await _run_git(*cmd, cwd=cwd)
    return _to_result(rc, stdout, stderr)


async def _handle_log(args: GitToolInput, cwd: Path) -> ToolResult:
    cmd: list[str] = ["log", f"--max-count={args.max_count}"]
    if args.oneline:
        cmd.append("--oneline")
    if args.ref:
        cmd.append(args.ref)
    if args.files:
        cmd.append("--")
        cmd.extend(args.files)
    rc, stdout, stderr = await _run_git(*cmd, cwd=cwd)
    return _to_result(rc, stdout, stderr)


async def _handle_show(args: GitToolInput, cwd: Path) -> ToolResult:
    cmd: list[str] = ["show", args.ref or "HEAD"]
    if args.files:
        cmd.append("--")
        cmd.extend(args.files)
    rc, stdout, stderr = await _run_git(*cmd, cwd=cwd)
    return _to_result(rc, stdout, stderr)


async def _handle_blame(args: GitToolInput, cwd: Path) -> ToolResult:
    assert args.files and len(args.files) == 1  # validated
    cmd: list[str] = ["blame"]
    if args.line_start is not None and args.line_end is not None:
        cmd.append(f"-L{args.line_start},{args.line_end}")
    elif args.line_start is not None:
        cmd.append(f"-L{args.line_start},")
    cmd.append("--")
    cmd.append(args.files[0])
    rc, stdout, stderr = await _run_git(*cmd, cwd=cwd)
    return _to_result(rc, stdout, stderr)


async def _handle_branch_list(args: GitToolInput, cwd: Path) -> ToolResult:
    del args
    rc, stdout, stderr = await _run_git("branch", "-a", "-v", cwd=cwd)
    return _to_result(rc, stdout, stderr)


async def _handle_add(args: GitToolInput, cwd: Path) -> ToolResult:
    assert args.files  # validated
    for f in args.files:
        if f.startswith("-"):
            return ToolResult(output=f"Invalid file path: {f!r}", is_error=True)
    rc, stdout, stderr = await _run_git("add", "--", *args.files, cwd=cwd)
    return _to_result(rc, stdout, stderr)


async def _handle_commit(args: GitToolInput, cwd: Path) -> ToolResult:
    assert args.message  # validated
    rc, stdout, stderr = await _run_git("commit", "-m", args.message, cwd=cwd)
    return _to_result(rc, stdout, stderr)


async def _handle_push(args: GitToolInput, cwd: Path) -> ToolResult:
    cmd: list[str] = ["push", args.remote]
    if args.ref:
        cmd.append(args.ref)
    rc, stdout, stderr = await _run_git(*cmd, cwd=cwd)
    return _to_result(rc, stdout, stderr)


async def _handle_pull(args: GitToolInput, cwd: Path) -> ToolResult:
    cmd: list[str] = ["pull", args.remote]
    if args.ref:
        cmd.append(args.ref)
    rc, stdout, stderr = await _run_git(*cmd, cwd=cwd)
    return _to_result(rc, stdout, stderr)


async def _handle_branch_create(args: GitToolInput, cwd: Path) -> ToolResult:
    assert args.ref  # validated
    cmd: list[str] = ["branch", args.ref]
    if args.start_point:
        cmd.append(args.start_point)
    rc, stdout, stderr = await _run_git(*cmd, cwd=cwd)
    return _to_result(rc, stdout, stderr)


async def _handle_branch_delete(args: GitToolInput, cwd: Path) -> ToolResult:
    assert args.ref  # validated
    rc, stdout, stderr = await _run_git("branch", "-d", args.ref, cwd=cwd)
    return _to_result(rc, stdout, stderr)


async def _handle_checkout(args: GitToolInput, cwd: Path) -> ToolResult:
    assert args.ref  # validated
    rc, stdout, stderr = await _run_git("checkout", args.ref, cwd=cwd)
    return _to_result(rc, stdout, stderr)


async def _handle_stash(args: GitToolInput, cwd: Path) -> ToolResult:
    action = args.stash_action
    if action == "push":
        cmd: list[str] = ["stash", "push"]
        if args.stash_message:
            cmd.extend(["-m", args.stash_message])
    elif action == "pop":
        cmd = ["stash", "pop"]
    elif action == "list":
        cmd = ["stash", "list"]
    elif action == "drop":
        cmd = ["stash", "drop"]
    else:
        return ToolResult(output=f"Unknown stash action: {action}", is_error=True)
    rc, stdout, stderr = await _run_git(*cmd, cwd=cwd)
    return _to_result(rc, stdout, stderr)


async def _handle_tag(args: GitToolInput, cwd: Path) -> ToolResult:
    assert args.ref and args.message  # validated
    rc, stdout, stderr = await _run_git(
        "tag", "-a", args.ref, "-m", args.message, cwd=cwd
    )
    return _to_result(rc, stdout, stderr)


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_DISPATCH: dict[str, object] = {
    "status": _handle_status,
    "diff": _handle_diff,
    "log": _handle_log,
    "show": _handle_show,
    "blame": _handle_blame,
    "branch_list": _handle_branch_list,
    "add": _handle_add,
    "commit": _handle_commit,
    "push": _handle_push,
    "pull": _handle_pull,
    "branch_create": _handle_branch_create,
    "branch_delete": _handle_branch_delete,
    "checkout": _handle_checkout,
    "stash": _handle_stash,
    "tag": _handle_tag,
}
