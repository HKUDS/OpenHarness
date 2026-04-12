"""Tests for sandbox path boundary validation."""

from __future__ import annotations

from pathlib import Path

from openharness.sandbox.path_validator import validate_sandbox_path


def test_path_within_cwd_allowed(tmp_path):
    cwd = tmp_path / "project"
    cwd.mkdir()
    target = cwd / "src" / "main.py"
    target.parent.mkdir(parents=True)
    target.touch()

    allowed, reason = validate_sandbox_path(target, cwd)
    assert allowed is True
    assert reason == ""


def test_path_outside_cwd_blocked(tmp_path):
    cwd = tmp_path / "project"
    cwd.mkdir()
    outside = tmp_path / "other" / "secret.txt"
    outside.parent.mkdir(parents=True)
    outside.touch()

    allowed, reason = validate_sandbox_path(outside, cwd)
    assert allowed is False
    assert "outside the sandbox boundary" in reason


def test_dotdot_traversal_blocked(tmp_path):
    cwd = tmp_path / "project"
    cwd.mkdir()
    (tmp_path / "secret.txt").touch()

    # Path that uses .. to escape
    traversal = cwd / ".." / "secret.txt"

    allowed, reason = validate_sandbox_path(traversal, cwd)
    assert allowed is False
    assert "outside the sandbox boundary" in reason


def test_symlink_escape_blocked(tmp_path):
    cwd = tmp_path / "project"
    cwd.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("sensitive")

    link = cwd / "link.txt"
    link.symlink_to(secret)

    allowed, reason = validate_sandbox_path(link, cwd)
    assert allowed is False
    assert "outside the sandbox boundary" in reason


def test_extra_allow_paths_respected(tmp_path):
    cwd = tmp_path / "project"
    cwd.mkdir()
    extra_dir = tmp_path / "shared"
    extra_dir.mkdir()
    target = extra_dir / "data.csv"
    target.touch()

    allowed, reason = validate_sandbox_path(target, cwd, extra_allowed=[str(extra_dir)])
    assert allowed is True


def test_relative_path_within_cwd(tmp_path):
    cwd = tmp_path / "project"
    cwd.mkdir()
    target = cwd / "file.py"
    target.touch()

    allowed, reason = validate_sandbox_path(target, cwd)
    assert allowed is True


def test_home_dir_blocked(tmp_path):
    cwd = tmp_path / "project"
    cwd.mkdir()
    home_file = Path.home() / ".ssh" / "id_rsa"

    allowed, reason = validate_sandbox_path(home_file, cwd)
    assert allowed is False
