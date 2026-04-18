"""Pluggable memory providers.

The default ``local`` provider wraps the existing project-memory search and
preserves byte-for-byte the prior behavior of :func:`build_runtime_system_prompt`.
Additional providers (HTTP, MCP, ...) register themselves via
:func:`register_memory_provider` and are selected by ``settings.memory.backend``.
"""

from __future__ import annotations

from openharness.memory.providers.base import (
    MemoryProvider,
    MemoryResult,
    clear_memory_providers,
    get_memory_provider,
    known_memory_providers,
    register_memory_provider,
)
from openharness.memory.providers.local import LocalMarkdownProvider


def _ensure_defaults() -> None:
    """Register the built-in ``local`` provider exactly once."""
    if "local" not in known_memory_providers():
        register_memory_provider("local", LocalMarkdownProvider)


_ensure_defaults()


__all__ = [
    "LocalMarkdownProvider",
    "MemoryProvider",
    "MemoryResult",
    "clear_memory_providers",
    "get_memory_provider",
    "known_memory_providers",
    "register_memory_provider",
]
