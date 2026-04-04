"""Tests for validate_worktree_slug edge cases and WorktreeManager helpers."""

from __future__ import annotations

import pytest

from openharness.swarm.worktree import (
    _flatten_slug,
    _worktree_branch,
    validate_worktree_slug,
)


# ---------------------------------------------------------------------------
# validate_worktree_slug — valid cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slug",
    [
        "simple",
        "with-dashes",
        "with_underscores",
        "alpha123",
        "a.b.c",
        "feature/my-task",
        "a/b/c",
        "A-Z_0-9.mixed",
        "x" * 64,  # exactly 64 chars
    ],
)
def test_validate_worktree_slug_valid(slug):
    assert validate_worktree_slug(slug) == slug


# ---------------------------------------------------------------------------
# validate_worktree_slug — invalid cases
# ---------------------------------------------------------------------------


def test_validate_empty_slug_raises():
    with pytest.raises(ValueError, match="empty"):
        validate_worktree_slug("")


def test_validate_too_long_slug_raises():
    with pytest.raises(ValueError, match="64"):
        validate_worktree_slug("x" * 65)


def test_validate_absolute_path_raises():
    with pytest.raises(ValueError, match="absolute"):
        validate_worktree_slug("/absolute/path")


def test_validate_backslash_absolute_raises():
    with pytest.raises(ValueError, match="absolute"):
        validate_worktree_slug("\\windows\\path")


def test_validate_dot_segment_raises():
    with pytest.raises(ValueError, match=r"\.|\.\."):
        validate_worktree_slug("a/./b")


def test_validate_dotdot_segment_raises():
    with pytest.raises(ValueError, match=r"\.|\.\."):
        validate_worktree_slug("a/../b")


def test_validate_invalid_chars_raises():
    with pytest.raises(ValueError):
        validate_worktree_slug("has space")


def test_validate_empty_segment_via_double_slash_raises():
    with pytest.raises(ValueError):
        validate_worktree_slug("a//b")


@pytest.mark.parametrize(
    "slug",
    [
        "has space",
        "has@symbol",
        "has!bang",
        "has$dollar",
        "has#hash",
        "has%percent",
    ],
)
def test_validate_various_invalid_chars(slug):
    with pytest.raises(ValueError):
        validate_worktree_slug(slug)


# ---------------------------------------------------------------------------
# _flatten_slug
# ---------------------------------------------------------------------------


def test_flatten_slug_replaces_slash_with_plus():
    assert _flatten_slug("feature/my-task") == "feature+my-task"


def test_flatten_slug_no_slash_unchanged():
    assert _flatten_slug("simple") == "simple"


def test_flatten_slug_multiple_slashes():
    assert _flatten_slug("a/b/c") == "a+b+c"


# ---------------------------------------------------------------------------
# _worktree_branch
# ---------------------------------------------------------------------------


def test_worktree_branch_simple():
    assert _worktree_branch("fix-bug") == "worktree-fix-bug"


def test_worktree_branch_with_slash():
    assert _worktree_branch("feature/foo") == "worktree-feature+foo"


def test_worktree_branch_prefix():
    branch = _worktree_branch("anything")
    assert branch.startswith("worktree-")
