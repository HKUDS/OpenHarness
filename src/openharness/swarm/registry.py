"""Backend registry for teammate execution."""

from __future__ import annotations

import logging
import os
import platform
import shutil
from typing import TYPE_CHECKING, Any

from openharness.swarm.spawn_utils import is_tmux_available
from openharness.swarm.types import BackendDetectionResult, BackendType, TeammateExecutor

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def _detect_tmux() -> bool:
    """Return True if the process is running inside an active tmux session.

    Checks:
    1. ``$TMUX`` environment variable (set by tmux for attached clients).
    2. The ``tmux`` binary is available on PATH.
    """
    if not os.environ.get("TMUX"):
        logger.debug("[BackendRegistry] _detect_tmux: $TMUX not set")
        return False
    if not shutil.which("tmux"):
        logger.debug("[BackendRegistry] _detect_tmux: tmux binary not found on PATH")
        return False
    logger.debug("[BackendRegistry] _detect_tmux: inside tmux session with binary available")
    return True


def _detect_iterm2() -> bool:
    """Return True if the process is running inside an iTerm2 terminal.

    Checks ``$ITERM_SESSION_ID`` which iTerm2 sets for every terminal session.
    """
    if os.environ.get("ITERM_SESSION_ID"):
        logger.debug("[BackendRegistry] _detect_iterm2: ITERM_SESSION_ID=%s", os.environ["ITERM_SESSION_ID"])
        return True
    logger.debug("[BackendRegistry] _detect_iterm2: ITERM_SESSION_ID not set")
    return False


def _is_it2_cli_available() -> bool:
    """Return True if the ``it2`` CLI is installed (used for iTerm2 pane control)."""
    available = shutil.which("it2") is not None
    logger.debug("[BackendRegistry] _is_it2_cli_available: %s", available)
    return available


def _get_tmux_install_instructions() -> str:
    """Return platform-specific tmux installation instructions."""
    system = platform.system().lower()
    if system == "darwin":
        return (
            "To use agent swarms, install tmux:\n"
            "  brew install tmux\n"
            "Then start a tmux session with: tmux new-session -s claude"
        )
    elif system == "linux":
        return (
            "To use agent swarms, install tmux:\n"
            "  sudo apt install tmux    # Ubuntu/Debian\n"
            "  sudo dnf install tmux    # Fedora/RHEL\n"
            "Then start a tmux session with: tmux new-session -s claude"
        )
    elif system == "windows":
        return (
            "To use agent swarms, you need tmux which requires WSL "
            "(Windows Subsystem for Linux).\n"
            "Install WSL first, then inside WSL run:\n"
            "  sudo apt install tmux\n"
            "Then start a tmux session with: tmux new-session -s claude"
        )
    else:
        return (
            "To use agent swarms, install tmux using your system's package manager.\n"
            "Then start a tmux session with: tmux new-session -s claude"
        )


# ---------------------------------------------------------------------------
# BackendRegistry
# ---------------------------------------------------------------------------


class BackendRegistry:
    """Registry that maps BackendType names to TeammateExecutor instances.

    Detection priority pipeline (mirrors ``registry.ts``):
    1. ``in_process`` – when explicitly requested or no pane backend available.
    2. ``tmux`` – when inside a tmux session and tmux binary present.
    3. ``subprocess`` – always available as the safe fallback.

    Usage::

        registry = BackendRegistry()
        executor = registry.get_executor()           # auto-detect best backend
        executor = registry.get_executor("in_process")  # explicit selection
    """

    def __init__(self) -> None:
        self._backends: dict[BackendType, TeammateExecutor] = {}
        self._detected: BackendType | None = None
        self._detection_result: BackendDetectionResult | None = None
        self._in_process_fallback_active: bool = False
        self._register_defaults()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_backend(self, executor: TeammateExecutor) -> None:
        """Register a custom executor under its declared ``type`` key."""
        self._backends[executor.type] = executor
        logger.debug("Registered backend: %s", executor.type)

    def detect_backend(self) -> BackendType:
        """Detect and cache the most capable available backend.

        Detection priority:
        1. ``in_process`` – if in-process fallback was previously activated.
        2. ``tmux`` – if inside an active tmux session and tmux binary present.
        3. ``subprocess`` – always available as the safe fallback.

        Returns:
            The detected :data:`BackendType` string.
        """
        if self._detected is not None:
            logger.debug(
                "[BackendRegistry] Using cached backend detection: %s", self._detected
            )
            return self._detected

        logger.debug("[BackendRegistry] Starting backend detection...")

        # Priority 1: in-process fallback (activated after a prior failed spawn)
        if self._in_process_fallback_active:
            logger.debug(
                "[BackendRegistry] in_process fallback active — selecting in_process"
            )
            self._detected = "in_process"
            self._detection_result = BackendDetectionResult(
                backend="in_process",
                is_native=True,
            )
            return self._detected

        # Priority 2: tmux (inside session + binary available)
        inside_tmux = _detect_tmux()
        if inside_tmux:
            if "tmux" in self._backends:
                logger.debug("[BackendRegistry] Selected: tmux (running inside tmux session)")
                self._detected = "tmux"
                self._detection_result = BackendDetectionResult(
                    backend="tmux",
                    is_native=True,
                )
                return self._detected
            else:
                logger.debug(
                    "[BackendRegistry] Inside tmux but TmuxBackend not registered — "
                    "falling through to subprocess"
                )

        # Priority 3: subprocess (always available)
        logger.debug("[BackendRegistry] Selected: subprocess (default fallback)")
        self._detected = "subprocess"
        self._detection_result = BackendDetectionResult(
            backend="subprocess",
            is_native=False,
        )
        return self._detected

    def detect_pane_backend(self) -> BackendDetectionResult:
        """Detect which pane backend (tmux / iTerm2) should be used.

        Implements the same priority flow as ``detectAndGetBackend()`` in the
        TypeScript source:

        1. If inside tmux, always use tmux.
        2. If in iTerm2 with ``it2`` CLI, use iTerm2.
        3. If in iTerm2 without ``it2`` but tmux available, use tmux.
        4. If in iTerm2 with no tmux, raise with setup instructions.
        5. If tmux binary available (external session), use tmux.
        6. Otherwise raise with platform-specific install instructions.

        Returns:
            :class:`BackendDetectionResult` describing the chosen pane backend.

        Raises:
            RuntimeError: When no pane backend is available.
        """
        logger.debug("[BackendRegistry] Starting pane backend detection...")

        in_tmux = _detect_tmux()
        in_iterm2 = _detect_iterm2()

        logger.debug(
            "[BackendRegistry] Environment: in_tmux=%s, in_iterm2=%s",
            in_tmux,
            in_iterm2,
        )

        # Priority 1: inside tmux — always use tmux
        if in_tmux:
            logger.debug("[BackendRegistry] Selected pane backend: tmux (inside tmux session)")
            return BackendDetectionResult(backend="tmux", is_native=True)

        # Priority 2: in iTerm2, try native panes
        if in_iterm2:
            it2_available = _is_it2_cli_available()
            logger.debug(
                "[BackendRegistry] iTerm2 detected, it2 CLI available: %s", it2_available
            )

            if it2_available:
                logger.debug("[BackendRegistry] Selected pane backend: iterm2 (native with it2 CLI)")
                return BackendDetectionResult(backend="iterm2", is_native=True)

            # it2 not available — can we fall back to tmux?
            tmux_bin = is_tmux_available()
            logger.debug(
                "[BackendRegistry] it2 not available, tmux binary available: %s", tmux_bin
            )

            if tmux_bin:
                logger.debug(
                    "[BackendRegistry] Selected pane backend: tmux (fallback in iTerm2, "
                    "it2 setup recommended)"
                )
                return BackendDetectionResult(
                    backend="tmux",
                    is_native=False,
                    needs_setup=True,
                )

            logger.debug(
                "[BackendRegistry] ERROR: in iTerm2 but no it2 CLI and no tmux"
            )
            raise RuntimeError(
                "iTerm2 detected but it2 CLI not installed.\n"
                "Install it2 with: pip install it2"
            )

        # Priority 3: not in tmux or iTerm2 — use tmux external session if available
        tmux_bin = is_tmux_available()
        logger.debug(
            "[BackendRegistry] Not in tmux or iTerm2, tmux binary available: %s", tmux_bin
        )

        if tmux_bin:
            logger.debug("[BackendRegistry] Selected pane backend: tmux (external session mode)")
            return BackendDetectionResult(backend="tmux", is_native=False)

        # No pane backend available
        logger.debug("[BackendRegistry] ERROR: No pane backend available")
        raise RuntimeError(_get_tmux_install_instructions())

    def get_executor(self, backend: BackendType | None = None) -> TeammateExecutor:
        """Return a TeammateExecutor for the given backend type.

        Args:
            backend: Explicit backend type to use. When *None* the registry
                     auto-detects the best available backend.

        Returns:
            The registered :class:`~openharness.swarm.types.TeammateExecutor`.

        Raises:
            KeyError: If the requested backend has not been registered.
        """
        resolved = backend or self.detect_backend()
        executor = self._backends.get(resolved)
        if executor is None:
            available = list(self._backends.keys())
            raise KeyError(
                f"Backend {resolved!r} is not registered. Available: {available}"
            )
        return executor

    def get_preferred_backend(self, config: dict | None = None) -> BackendType:
        """Return the user-preferred backend from settings / config.

        Falls back to auto-detection when no explicit preference is set.

        Args:
            config: Optional settings dict. Reads ``teammate_mode`` key if
                    present (values: ``"auto"``, ``"in_process"``, ``"tmux"``).

        Returns:
            The resolved :data:`BackendType`.
        """
        if config:
            mode = config.get("teammate_mode", "auto")
        else:
            mode = os.environ.get("OPENHARNESS_TEAMMATE_MODE", "auto")

        logger.debug("[BackendRegistry] get_preferred_backend: mode=%s", mode)

        if mode == "in_process":
            return "in_process"
        elif mode == "tmux":
            return "tmux"
        else:
            # "auto" — fall through to detection
            return self.detect_backend()

    def mark_in_process_fallback(self) -> None:
        """Record that spawn fell back to in-process mode.

        Called when no pane backend was available. After this,
        ``get_executor()`` will keep returning the in-process backend for the
        lifetime of the process (the environment won't change mid-session).
        """
        logger.debug("[BackendRegistry] Marking in-process fallback as active")
        self._in_process_fallback_active = True
        # Invalidate cached detection so the next call re-detects
        self._detected = None
        self._detection_result = None

    def get_cached_detection_result(self) -> BackendDetectionResult | None:
        """Return the cached :class:`BackendDetectionResult`, or *None* if not yet detected."""
        return self._detection_result

    def available_backends(self) -> list[BackendType]:
        """Return sorted list of registered backend types."""
        return sorted(self._backends.keys())  # type: ignore[return-value]

    def health_check(self) -> dict[str, Any]:
        """Check the health of all registered backends.

        Returns:
            Dict with backend_name -> {available: bool, type: str} mapping,
            plus a total_count of available backends.
        """
        results: dict[str, dict[str, Any]] = {}
        available_count = 0

        for backend_type, executor in self._backends.items():
            is_available = executor.is_available()
            results[backend_type] = {
                "available": is_available,
                "type": str(executor.type),
            }
            if is_available:
                available_count += 1

        return {
            "backends": results,
            "total_count": available_count,
        }

    def reset(self) -> None:
        """Clear detection cache and re-register defaults.

        Intended for testing — allows re-detection after env changes.
        """
        self._detected = None
        self._detection_result = None
        self._in_process_fallback_active = False
        self._backends.clear()
        self._register_defaults()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register_defaults(self) -> None:
        """Register built-in backends that are unconditionally available."""
        from openharness.swarm.subprocess_backend import SubprocessBackend
        from openharness.swarm.in_process import InProcessBackend

        self._backends["subprocess"] = SubprocessBackend()
        self._backends["in_process"] = InProcessBackend()

        # Tmux backend registration is deferred until implementation exists.
        # If a TmuxBackend is available it can be registered via register_backend().


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: BackendRegistry | None = None


def get_backend_registry() -> BackendRegistry:
    """Return the process-wide singleton BackendRegistry."""
    global _registry
    if _registry is None:
        _registry = BackendRegistry()
    return _registry


def mark_in_process_fallback() -> None:
    """Module-level convenience: mark in-process fallback on the singleton registry."""
    get_backend_registry().mark_in_process_fallback()
