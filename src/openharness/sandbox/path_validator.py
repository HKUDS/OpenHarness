"""Path boundary enforcement for sandbox file operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


def validate_sandbox_path(
    path: Path,
    cwd: Path,
    extra_allowed: list[str] | None = None,
) -> tuple[bool, str]:
    """Check whether *path* falls within the sandbox boundary.

    Returns ``(True, "")`` when the path is allowed, or ``(False, reason)``
    when it falls outside the permitted directories.
    """
    resolved = path.resolve()
    resolved_cwd = cwd.resolve()

    # Primary check: path must be within the project directory
    try:
        resolved.relative_to(resolved_cwd)
        return True, ""
    except ValueError:
        pass

    # Secondary: check extra allowed paths (from filesystem settings)
    for allowed in extra_allowed or []:
        allowed_path = Path(allowed).expanduser().resolve()
        try:
            resolved.relative_to(allowed_path)
            return True, ""
        except ValueError:
            continue

    return False, f"path {resolved} is outside the sandbox boundary ({resolved_cwd})"


# Metadata keys recognised on ``ToolExecutionContext.metadata`` to configure the
# default workspace-containment guard applied by the built-in file tools.
WORKSPACE_RESTRICT_METADATA_KEY = "restrict_to_workspace"
WORKSPACE_ROOT_METADATA_KEY = "workspace_root"
WORKSPACE_ALLOW_PATHS_METADATA_KEY = "workspace_allow_paths"


def validate_workspace_path(
    path: Path,
    cwd: Path,
    metadata: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    """Check whether a built-in file tool may touch *path*.

    This is the always-on counterpart to :func:`validate_sandbox_path`: it
    keeps model-/LLM-supplied file reads and writes inside the workspace root
    even when the optional Docker sandbox is not active, which is the default
    configuration.  The check reuses the same containment logic as the sandbox
    path validator (real-path resolution plus an ancestor-containment check),
    so absolute paths outside the root, ``..`` escapes, and symlinks that point
    outside the root are all rejected.

    Containment is enabled by default.  It can be turned off for a session by
    setting ``restrict_to_workspace`` to a falsey value in the tool execution
    metadata (an explicit operator opt-out), and additional roots can be
    permitted via ``workspace_allow_paths``.  ``workspace_root`` overrides the
    containment root (defaulting to ``cwd``).

    Returns ``(True, "")`` when the path is allowed, or ``(False, reason)``
    when it is outside the permitted directories.
    """
    metadata = metadata or {}

    # Default-safe: containment is on unless explicitly disabled.
    if WORKSPACE_RESTRICT_METADATA_KEY in metadata and not metadata[WORKSPACE_RESTRICT_METADATA_KEY]:
        return True, ""

    root_override = metadata.get(WORKSPACE_ROOT_METADATA_KEY)
    root = Path(root_override) if root_override else cwd

    extra_allowed = metadata.get(WORKSPACE_ALLOW_PATHS_METADATA_KEY)
    if isinstance(extra_allowed, (str, Path)):
        extra_allowed = [str(extra_allowed)]
    elif extra_allowed is not None:
        extra_allowed = [str(item) for item in extra_allowed]

    allowed, reason = validate_sandbox_path(path, root, extra_allowed)
    if allowed:
        return True, ""
    return False, (
        f"path {path.resolve()} is outside the workspace root ({root.resolve()}); "
        "set permission/path rules or disable workspace containment to allow it"
    )
