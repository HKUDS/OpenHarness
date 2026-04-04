"""Shared utilities for spawning teammate processes."""

from __future__ import annotations

import os
import shlex
import shutil
import sys


# Environment variable to override the teammate command
TEAMMATE_COMMAND_ENV_VAR = "OPENHARNESS_TEAMMATE_COMMAND"


# ---------------------------------------------------------------------------
# Environment variables forwarded to spawned teammates.
#
# Tmux may start a fresh login shell that does NOT inherit the parent
# process environment, so we forward any of these that are set.
# ---------------------------------------------------------------------------

_TEAMMATE_ENV_VARS = [
    # --- API provider selection -------------------------------------------
    # Without these, teammates would default to the wrong endpoint provider
    # and fail all API calls (analogous to GitHub issue #23561 in the TS source).
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
    # --- Config directory override ----------------------------------------
    # Allows operator-level config to be visible inside teammate processes.
    "CLAUDE_CONFIG_DIR",
    # --- Remote / CCR markers ---------------------------------------------
    # CCR-aware code paths check CLAUDE_CODE_REMOTE.  Auth finds its own
    # way; the FD env var wouldn't help across tmux boundaries anyway.
    "CLAUDE_CODE_REMOTE",
    # Auto-memory gate checks REMOTE && !MEMORY_DIR to disable memory on
    # ephemeral CCR filesystems.  Forwarding REMOTE alone would flip
    # teammates to memory-off when the parent has it on.
    "CLAUDE_CODE_REMOTE_MEMORY_DIR",
    # --- Upstream proxy settings ------------------------------------------
    # The parent's MITM relay is reachable from teammates on the same
    # container network.  Forward proxy vars so teammates route
    # customer-configured traffic through the relay for credential injection.
    # Without these, teammates bypass the proxy entirely.
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "NO_PROXY",
    "no_proxy",
    # --- CA bundle overrides ----------------------------------------------
    # Custom CA certificates must be visible to teammates when TLS inspection
    # is in use; missing these causes SSL verification failures.
    "SSL_CERT_FILE",
    "NODE_EXTRA_CA_CERTS",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
]


def get_teammate_command() -> str:
    """Return the executable used to spawn teammate processes.

    Resolution order:
    1. ``OPENHARNESS_TEAMMATE_COMMAND`` environment variable — allows the
       operator to point at a specific binary or wrapper script.
    2. The ``openharness`` entry-point on PATH (installed package mode).
    3. The current Python interpreter running the ``openharness`` module
       (development / editable-install fallback).
    """
    override = os.environ.get(TEAMMATE_COMMAND_ENV_VAR)
    if override:
        return override

    # Check if we are running as an installed package with an entry-point.
    entry_point = shutil.which("openharness")
    if entry_point:
        return entry_point

    # Fall back to the Python interpreter that is currently running this code.
    return sys.executable


def build_inherited_cli_flags(
    *,
    model: str | None = None,
    permission_mode: str | None = None,
    plan_mode_required: bool = False,
    settings_path: str | None = None,
    teammate_mode: str | None = None,
    plugin_dirs: list[str] | None = None,
    extra_flags: list[str] | None = None,
) -> list[str]:
    """Build CLI flags to propagate from the current session to spawned teammates.

    Ensures teammates inherit important settings like permission mode, model
    selection, and plugin configuration from their parent.

    All flag values are shell-quoted with :func:`shlex.quote` to prevent
    command injection when the resulting list is later joined into a shell
    command string.

    Args:
        model: Model override to forward (e.g. ``"claude-opus-4-6"``).
        permission_mode: One of ``"bypassPermissions"``, ``"acceptEdits"``, or None.
        plan_mode_required: When True, bypass-permissions flag is suppressed
            (plan mode takes precedence over bypass for safety).
        settings_path: Path to a settings JSON file to propagate via
            ``--settings``.  Shell-quoted for safety.
        teammate_mode: Teammate execution mode (``"auto"``, ``"in_process"``,
            ``"tmux"``).  Forwarded as ``--teammate-mode`` so tmux teammates
            use the same mode as the leader.
        plugin_dirs: List of plugin directory paths.  Each is forwarded as a
            separate ``--plugin-dir <path>`` flag so inline plugins are
            visible inside teammate processes.
        extra_flags: Additional pre-built flag strings to append verbatim.
            Callers are responsible for quoting any values in these strings.

    Returns:
        List of CLI flag strings ready to be passed to :mod:`subprocess`.
    """
    flags: list[str] = ["--headless"]

    # --- Permission mode ---------------------------------------------------
    # Plan mode takes precedence over bypass permissions for safety.
    if not plan_mode_required:
        if permission_mode == "bypassPermissions":
            flags.append("--dangerously-skip-permissions")
        elif permission_mode == "acceptEdits":
            flags.extend(["--permission-mode", "acceptEdits"])

    # --- Model override ----------------------------------------------------
    if model:
        flags.extend(["--model", shlex.quote(model)])

    # --- Settings path propagation ----------------------------------------
    # Ensures teammates load the same settings JSON as the leader process.
    if settings_path:
        flags.extend(["--settings", shlex.quote(settings_path)])

    # --- Plugin directories -----------------------------------------------
    # Each enabled plugin directory is forwarded individually so that inline
    # plugins (loaded via --plugin-dir) are available inside teammates.
    for plugin_dir in plugin_dirs or []:
        flags.extend(["--plugin-dir", shlex.quote(plugin_dir)])

    # --- Teammate mode propagation ----------------------------------------
    # Forwards the session-level teammate mode so tmux-spawned teammates do
    # not re-detect the mode independently and possibly choose a different one.
    if teammate_mode:
        flags.extend(["--teammate-mode", shlex.quote(teammate_mode)])

    if extra_flags:
        flags.extend(extra_flags)

    return flags


def build_inherited_env_vars() -> dict[str, str]:
    """Build environment variables to forward to spawned teammates.

    Always includes ``OPENHARNESS_AGENT_TEAMS=1`` plus any provider/proxy
    vars that are set in the current process.

    Returns:
        Dict of env var name → value to merge into the subprocess environment.
    """
    env: dict[str, str] = {
        "OPENHARNESS_AGENT_TEAMS": "1",
    }

    for key in _TEAMMATE_ENV_VARS:
        value = os.environ.get(key)
        if value:
            env[key] = value

    return env


def is_tmux_available() -> bool:
    """Return True if the ``tmux`` binary is on PATH."""
    return shutil.which("tmux") is not None


def is_inside_tmux() -> bool:
    """Return True if the current process is running inside a tmux session."""
    return bool(os.environ.get("TMUX"))
