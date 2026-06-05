"""Tests for openharness.permissions.path_policy (sandbox layer L1)."""

from __future__ import annotations

from pathlib import Path

from openharness.config.settings import SandboxFilesystemSettings, SandboxSettings
from openharness.permissions.modes import PermissionMode
from openharness.permissions.path_policy import PathPolicy, build_path_policy


def _policy(mode: PermissionMode, cwd: Path, **fs) -> PathPolicy:
    return PathPolicy(mode, SandboxFilesystemSettings(**fs), cwd)


def test_plan_mode_blocks_all_writes(tmp_path: Path):
    p = _policy(PermissionMode.PLAN, tmp_path)
    assert p.is_write_allowed(tmp_path / "file.txt").allowed is False


def test_default_mode_allows_within_cwd(tmp_path: Path):
    p = _policy(PermissionMode.DEFAULT, tmp_path)
    assert p.is_write_allowed(tmp_path / "sub" / "file.txt").allowed is True


def test_default_mode_blocks_outside_cwd(tmp_path: Path):
    p = _policy(PermissionMode.DEFAULT, tmp_path)
    assert p.is_write_allowed(tmp_path.parent / "outside.txt").allowed is False


def test_default_mode_blocks_parent_escape(tmp_path: Path):
    # cwd/../escape resolves outside the workspace root -> denied.
    p = _policy(PermissionMode.DEFAULT, tmp_path)
    assert p.is_write_allowed(tmp_path / ".." / "escape.txt").allowed is False


def test_full_auto_allows_outside_cwd(tmp_path: Path):
    p = _policy(PermissionMode.FULL_AUTO, tmp_path)
    assert p.is_write_allowed(tmp_path.parent / "anywhere.txt").allowed is True


def test_sensitive_paths_blocked_in_every_tier(tmp_path: Path):
    sensitive = tmp_path / ".ssh" / "id_rsa"
    for mode in (PermissionMode.DEFAULT, PermissionMode.FULL_AUTO, PermissionMode.PLAN):
        decision = _policy(mode, tmp_path).is_write_allowed(sensitive)
        assert decision.allowed is False, mode
        assert "sensitive" in decision.reason


def test_full_auto_still_blocks_sensitive(tmp_path: Path):
    # Decision D4: even full-access cannot write SSH/cloud credential paths.
    p = _policy(PermissionMode.FULL_AUTO, tmp_path)
    assert p.is_write_allowed(tmp_path / ".aws" / "credentials").allowed is False


def test_deny_write_glob_blocks_even_within_cwd(tmp_path: Path):
    p = _policy(PermissionMode.DEFAULT, tmp_path, allow_write=["."], deny_write=["*/secret/*"])
    assert p.is_write_allowed(tmp_path / "secret" / "key.txt").allowed is False


def test_deny_write_overrides_full_auto(tmp_path: Path):
    p = _policy(PermissionMode.FULL_AUTO, tmp_path, deny_write=["*/protected/*"])
    assert p.is_write_allowed(tmp_path.parent / "protected" / "x").allowed is False


def test_reads_allowed_by_default(tmp_path: Path):
    p = _policy(PermissionMode.DEFAULT, tmp_path)
    assert p.is_read_allowed(tmp_path.parent / "anything.txt").allowed is True


def test_reads_block_sensitive(tmp_path: Path):
    p = _policy(PermissionMode.DEFAULT, tmp_path)
    assert p.is_read_allowed(tmp_path / ".gnupg" / "secring.gpg").allowed is False


def test_deny_read_glob(tmp_path: Path):
    p = _policy(PermissionMode.DEFAULT, tmp_path, deny_read=["*.env"])
    assert p.is_read_allowed(tmp_path / "prod.env").allowed is False


def test_build_path_policy_from_sandbox_settings(tmp_path: Path):
    # SandboxSettings default allow_write=["."] -> cwd writable, outside not.
    policy = build_path_policy(PermissionMode.DEFAULT, SandboxSettings(), tmp_path)
    assert policy.is_write_allowed(tmp_path / "f.txt").allowed is True
    assert policy.is_write_allowed(tmp_path.parent / "f.txt").allowed is False
