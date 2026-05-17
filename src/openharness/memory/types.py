"""Memory-related data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MemoryHeader:
    """Metadata for one memory file."""

    path: Path
    title: str
    description: str
    modified_at: float
    memory_type: str = ""
    body_preview: str = ""
    id: str = ""
    schema_version: int = 0
    category: str = ""
    importance: int = 0
    source: str = ""
    signature: str = ""
    created_at: str = ""
    updated_at: str = ""
    ttl_days: int | None = None
    disabled: bool = False
    supersedes: tuple[str, ...] = ()
    relative_path: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    frontmatter: dict[str, Any] = field(default_factory=dict)
