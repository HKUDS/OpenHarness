"""Memory store provider abstraction."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, Callable, Protocol

from openharness.memory.types import MemoryHeader


class MemoryStoreProvider(Protocol):
    """Abstract durable memory backend."""

    def scan_memory_files(self, cwd: str | Path, *, max_files: int | None = 50) -> list[MemoryHeader]:
        """Return memory headers for the project."""

    def list_memory_files(self, cwd: str | Path) -> list[Path]:
        """Return memory document paths for the project."""

    def upsert_memory_entry(
        self,
        cwd: str | Path,
        *,
        key: str,
        title: str,
        content: str,
        description: str = "",
        memory_type: str = "",
    ) -> tuple[Path, str]:
        """Create or update one durable memory entry."""

    def add_memory_entry(self, cwd: str | Path, title: str, content: str) -> Path:
        """Append one manual memory entry."""

    def remove_memory_entry(self, cwd: str | Path, name: str) -> bool:
        """Delete one durable memory entry."""


MemoryProviderFactory = Callable[[str | Path, Any | None], MemoryStoreProvider]


class FileMemoryStoreProvider:
    """Default durable memory backend backed by the local filesystem."""

    def scan_memory_files(self, cwd: str | Path, *, max_files: int | None = 50) -> list[MemoryHeader]:
        from openharness.memory.scan import scan_memory_files_in_file_store

        return scan_memory_files_in_file_store(cwd, max_files=max_files)

    def list_memory_files(self, cwd: str | Path) -> list[Path]:
        return [header.path for header in self.scan_memory_files(cwd, max_files=None)]

    def upsert_memory_entry(
        self,
        cwd: str | Path,
        *,
        key: str,
        title: str,
        content: str,
        description: str = "",
        memory_type: str = "",
    ) -> tuple[Path, str]:
        from openharness.memory.manager import upsert_memory_entry_in_file_store

        return upsert_memory_entry_in_file_store(
            cwd,
            key=key,
            title=title,
            content=content,
            description=description,
            memory_type=memory_type,
        )

    def add_memory_entry(self, cwd: str | Path, title: str, content: str) -> Path:
        from openharness.memory.manager import add_memory_entry_in_file_store

        return add_memory_entry_in_file_store(cwd, title, content)

    def remove_memory_entry(self, cwd: str | Path, name: str) -> bool:
        from openharness.memory.manager import remove_memory_entry_in_file_store

        return remove_memory_entry_in_file_store(cwd, name)


_DEFAULT_PROVIDER: MemoryStoreProvider | None = None
_PROVIDER_OVERRIDES: dict[Path, MemoryStoreProvider] = {}
_PROVIDER_FACTORIES: dict[str, MemoryProviderFactory] = {}
_PROVIDER_LOCK = RLock()


def _normalize_root(root: str | Path) -> Path:
    return Path(root).expanduser().resolve()


def _normalize_provider_name(name: str) -> str:
    return name.strip().lower()


def _file_memory_provider_factory(cwd: str | Path, settings: Any | None = None) -> MemoryStoreProvider:
    del cwd, settings
    return FileMemoryStoreProvider()


def register_memory_provider_factory(name: str, factory: MemoryProviderFactory) -> str:
    """Register a named provider factory for runtime selection."""
    normalized = _normalize_provider_name(name)
    with _PROVIDER_LOCK:
        _PROVIDER_FACTORIES[normalized] = factory
    return normalized


def unregister_memory_provider_factory(name: str) -> None:
    """Remove a named provider factory."""
    normalized = _normalize_provider_name(name)
    with _PROVIDER_LOCK:
        if normalized == "file":
            _PROVIDER_FACTORIES[normalized] = _file_memory_provider_factory
            return
        _PROVIDER_FACTORIES.pop(normalized, None)


def list_memory_provider_names() -> tuple[str, ...]:
    """Return the available named memory backends."""
    with _PROVIDER_LOCK:
        if "file" not in _PROVIDER_FACTORIES:
            _PROVIDER_FACTORIES["file"] = _file_memory_provider_factory
        return tuple(sorted(_PROVIDER_FACTORIES))


def create_memory_provider(
    provider_name: str,
    cwd: str | Path,
    *,
    settings: Any | None = None,
) -> MemoryStoreProvider:
    """Instantiate a named provider backend."""
    normalized = _normalize_provider_name(provider_name or "file")
    with _PROVIDER_LOCK:
        if "file" not in _PROVIDER_FACTORIES:
            _PROVIDER_FACTORIES["file"] = _file_memory_provider_factory
        factory = _PROVIDER_FACTORIES.get(normalized)
    if factory is None:
        available = ", ".join(list_memory_provider_names())
        raise ValueError(f"Unknown memory provider: {provider_name}. Available providers: {available}")
    return factory(cwd, settings)


def configure_memory_provider(
    cwd: str | Path,
    provider_name: str,
    *,
    settings: Any | None = None,
) -> MemoryStoreProvider:
    """Create and register the active provider for one project root."""
    provider = create_memory_provider(provider_name, cwd, settings=settings)
    register_memory_provider(cwd, provider)
    return provider


def get_default_memory_provider() -> MemoryStoreProvider:
    """Return the default durable memory backend."""
    global _DEFAULT_PROVIDER
    with _PROVIDER_LOCK:
        if "file" not in _PROVIDER_FACTORIES:
            _PROVIDER_FACTORIES["file"] = _file_memory_provider_factory
        if _DEFAULT_PROVIDER is None:
            _DEFAULT_PROVIDER = FileMemoryStoreProvider()
        return _DEFAULT_PROVIDER


def set_default_memory_provider(provider: MemoryStoreProvider | None) -> None:
    """Override the default durable memory backend."""
    global _DEFAULT_PROVIDER
    with _PROVIDER_LOCK:
        _DEFAULT_PROVIDER = provider


def register_memory_provider(root: str | Path, provider: MemoryStoreProvider) -> Path:
    """Register a provider override for one project root."""
    normalized = _normalize_root(root)
    with _PROVIDER_LOCK:
        _PROVIDER_OVERRIDES[normalized] = provider
    return normalized


def unregister_memory_provider(root: str | Path) -> None:
    """Remove a provider override for one project root."""
    normalized = _normalize_root(root)
    with _PROVIDER_LOCK:
        _PROVIDER_OVERRIDES.pop(normalized, None)


def reset_memory_provider_registry() -> None:
    """Reset all provider overrides and restore the default file backend."""
    global _DEFAULT_PROVIDER
    with _PROVIDER_LOCK:
        _PROVIDER_OVERRIDES.clear()
        _DEFAULT_PROVIDER = None


def get_memory_provider(cwd: str | Path) -> MemoryStoreProvider:
    """Resolve the active durable memory backend for one workspace path."""
    normalized = _normalize_root(cwd)
    with _PROVIDER_LOCK:
        for root in sorted(_PROVIDER_OVERRIDES, key=lambda item: len(item.parts), reverse=True):
            try:
                normalized.relative_to(root)
            except ValueError:
                continue
            return _PROVIDER_OVERRIDES[root]
    return get_default_memory_provider()


__all__ = [
    "configure_memory_provider",
    "create_memory_provider",
    "FileMemoryStoreProvider",
    "list_memory_provider_names",
    "MemoryProviderFactory",
    "MemoryStoreProvider",
    "get_default_memory_provider",
    "get_memory_provider",
    "register_memory_provider_factory",
    "register_memory_provider",
    "reset_memory_provider_registry",
    "set_default_memory_provider",
    "unregister_memory_provider_factory",
    "unregister_memory_provider",
]