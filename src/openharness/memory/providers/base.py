"""Memory provider protocol and registry.

The provider protocol is intentionally synchronous for this first iteration
so it drops into the existing :func:`build_runtime_system_prompt` hot path
without forcing an async refactor of the prompt assembler. Providers that
perform network I/O should apply their own short timeout and return an empty
list on failure — the caller treats a provider exception as "no memories"
rather than failing the prompt build.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable


@dataclass(frozen=True)
class MemoryResult:
    """A single memory entry returned by a :class:`MemoryProvider`.

    ``content`` is the full body to inject into the system prompt; the caller
    does not re-read from disk or re-fetch from the provider. ``source``
    identifies which provider produced the result (useful for debugging and
    for provenance labeling in the prompt). ``metadata`` is provider-specific
    and opaque to the harness.
    """

    id: str
    title: str
    content: str
    description: str = ""
    score: float | None = None
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class MemoryProvider(Protocol):
    """Retrieve memory entries relevant to a query.

    Implementations must be safe to call once per user turn — the current
    call site runs inside the synchronous prompt-assembly path. Anything
    slower than ~100 ms is likely to be user-perceptible; providers that talk
    to a remote service should either cache or bound their work with a tight
    timeout and fail open (return ``[]``).
    """

    name: str

    def search(
        self,
        query: str,
        *,
        cwd: str | Path,
        limit: int = 5,
    ) -> list[MemoryResult]:
        """Return up to ``limit`` results most relevant to ``query``."""
        ...

    def close(self) -> None:
        """Release any held resources. No-op for stateless providers."""
        ...


ProviderFactory = Callable[..., MemoryProvider]

# Module-level registry. Kept private; callers go through the helpers below
# so provider resolution can grow additional behavior (e.g. caching, plugin
# discovery) without touching every call site.
_REGISTRY: dict[str, ProviderFactory] = {}


def register_memory_provider(name: str, factory: ProviderFactory) -> None:
    """Register a memory provider factory under ``name``.

    Raises ``ValueError`` if ``name`` is already registered. Silent
    replacement makes plugin conflicts hard to debug; a future PR can add an
    explicit ``override=True`` parameter when a real use case arises.
    """
    if not name:
        raise ValueError("Memory provider name must be non-empty")
    if name in _REGISTRY:
        raise ValueError(f"Memory provider '{name}' is already registered")
    _REGISTRY[name] = factory


def get_memory_provider(name: str, *, settings: Any | None = None) -> MemoryProvider:
    """Instantiate the memory provider registered under ``name``.

    ``settings`` is the Settings object (duck-typed so tests can pass a
    stub). The provider's configuration is looked up under
    ``settings.memory.providers[name]`` and forwarded as kwargs to the
    factory. Unknown backends raise ``ValueError`` with a descriptive
    message listing the known names.
    """
    if name not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY)) or "<none registered>"
        raise ValueError(
            f"Unknown memory backend '{name}'. "
            f"Known backends: {known}. "
            f"Set memory.backend in settings.json to one of the known values."
        )
    factory = _REGISTRY[name]
    provider_config: dict[str, Any] = {}
    if settings is not None:
        providers = getattr(getattr(settings, "memory", None), "providers", {}) or {}
        provider_config = dict(providers.get(name, {}) or {})
    return factory(**provider_config)


def known_memory_providers() -> list[str]:
    """Return the sorted list of registered backend names."""
    return sorted(_REGISTRY)


def clear_memory_providers() -> None:
    """Reset the provider registry. Intended for tests only."""
    _REGISTRY.clear()
