"""In-process filesystem path policy (sandbox layer L1).

Single, platform-independent answer to "may a tool write/read this path?",
derived from the permission mode + the sandbox filesystem settings. This is the
enforcement layer that the in-process file tools (write_file / edit_file) must
consult before touching the filesystem — today they don't, so an approved
mutating tool can write anywhere the user can. It does NOT do OS-level syscall
sandboxing (that is the bash-subprocess layer, L2); see
``plans/os-sandbox.plan.md`` for the full two-layer design.

Tier mapping (plan decision D3):
    plan      -> read-only       (no writes anywhere)
    default   -> workspace-write  (writes within allow_write roots, minus deny_write)
    full_auto -> full-access      (writes anywhere EXCEPT the sensitive denylist)

The built-in ``SENSITIVE_PATH_PATTERNS`` denylist (~/.ssh, ~/.aws/credentials,
~/.gnupg, OH's own credential stores, …) is enforced in EVERY tier, including
``full_auto`` (decision D4), as defence-in-depth against prompt-injection-directed
credential access. Disabling even that would require a separate explicit opt-in.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

from openharness.config.settings import SandboxFilesystemSettings, SandboxSettings
from openharness.permissions.checker import SENSITIVE_PATH_PATTERNS
from openharness.permissions.modes import PermissionMode


@dataclass(frozen=True)
class PathDecision:
    """Whether a path operation is permitted, with a human-readable reason."""

    allowed: bool
    reason: str = ""


def _match_forms(path_str: str) -> tuple[str, ...]:
    """Path forms used for glob matching.

    Mirror ``permissions.checker._policy_match_paths``: append a trailing slash so
    directory-rooted patterns like ``*/.ssh/*`` also match the directory itself.
    """
    normalized = path_str.rstrip("/")
    if not normalized:
        return (path_str,)
    return (normalized, normalized + "/")


def _first_match(path_forms: tuple[str, ...], patterns: list[str] | tuple[str, ...]) -> str | None:
    for candidate in path_forms:
        for pattern in patterns:
            if isinstance(pattern, str) and fnmatch.fnmatch(candidate, pattern):
                return pattern
    return None


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class PathPolicy:
    """Resolved per-session filesystem policy (mode + sandbox fs settings + cwd)."""

    def __init__(
        self,
        mode: PermissionMode,
        filesystem: SandboxFilesystemSettings,
        cwd: str | Path,
    ) -> None:
        self._mode = mode
        self._fs = filesystem
        self._cwd = Path(cwd).resolve()
        # allow_write entries ("." and other relative ones) resolve against cwd.
        self._write_roots = [self._resolve(entry) for entry in (filesystem.allow_write or [])]

    def _resolve(self, file_path: str | Path) -> Path:
        p = Path(file_path)
        if not p.is_absolute():
            p = self._cwd / p
        # Resolve symlinks + ".." so an escape like cwd/../../etc/x can't slip past
        # the workspace-root containment check. strict=False: target may not exist.
        return p.resolve()

    def is_write_allowed(self, file_path: str | Path) -> PathDecision:
        resolved = self._resolve(file_path)
        forms = _match_forms(str(resolved))

        # 1. Sensitive denylist — enforced in EVERY tier, incl. full_auto (D4).
        hit = _first_match(forms, SENSITIVE_PATH_PATTERNS)
        if hit is not None:
            return PathDecision(False, f"{resolved} is a sensitive credential path (pattern '{hit}')")

        # 2. Explicit deny_write globs — always deny.
        hit = _first_match(forms, self._fs.deny_write or [])
        if hit is not None:
            return PathDecision(False, f"{resolved} matches deny_write pattern '{hit}'")

        # 3. Tier.
        if self._mode == PermissionMode.PLAN:
            return PathDecision(False, "plan mode is read-only; writes are blocked")
        if self._mode == PermissionMode.FULL_AUTO:
            return PathDecision(True, "full-access mode")
        # default -> workspace-write: must live under an allow_write root.
        if any(_is_within(resolved, root) for root in self._write_roots):
            return PathDecision(True, "within an allowed write root")
        roots = [str(r) for r in self._write_roots]
        return PathDecision(False, f"{resolved} is outside the allowed write roots {roots}")

    def is_read_allowed(self, file_path: str | Path) -> PathDecision:
        resolved = self._resolve(file_path)
        forms = _match_forms(str(resolved))

        hit = _first_match(forms, SENSITIVE_PATH_PATTERNS)
        if hit is not None:
            return PathDecision(False, f"{resolved} is a sensitive credential path (pattern '{hit}')")
        hit = _first_match(forms, self._fs.deny_read or [])
        if hit is not None:
            return PathDecision(False, f"{resolved} matches deny_read pattern '{hit}'")
        return PathDecision(True, "reads allowed")


def build_path_policy(
    mode: PermissionMode,
    sandbox: SandboxSettings,
    cwd: str | Path,
) -> PathPolicy:
    """Construct a :class:`PathPolicy` from a ``SandboxSettings`` + mode + cwd."""
    return PathPolicy(mode, sandbox.filesystem, cwd)
