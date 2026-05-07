"""Compatibility helpers shared by channel implementations.

Historically several channel adapters imported small utility functions from
``openharness.utils.helpers``.  Keep this module narrow and dependency-free so
optional channel imports do not fail in installed packages.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from openharness.config.paths import get_data_dir

__all__ = ["get_data_path", "safe_filename", "split_message"]


def get_data_path() -> Path:
    """Return OpenHarness' data directory.

    This is a backwards-compatible alias used by older channel code.
    """

    return get_data_dir()


def split_message(text: str, max_length: int) -> list[str]:
    """Split text into chunks no longer than ``max_length`` characters.

    The splitter prefers newline and whitespace boundaries, but will hard-split
    long unbroken text. Empty input produces no chunks.
    """

    if max_length <= 0:
        raise ValueError("max_length must be positive")
    if not text:
        return []
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_length:
        split_at = remaining.rfind("\n", 0, max_length + 1)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, max_length + 1)
        if split_at <= 0:
            split_at = max_length

        chunk = remaining[:split_at].rstrip()
        if not chunk:
            chunk = remaining[:max_length]
            split_at = max_length
        chunks.append(chunk)
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)
    return chunks


def safe_filename(value: object, *, max_length: int = 128) -> str:
    """Return a conservative filename-safe representation of ``value``.

    Path separators, control characters, shell metacharacters, and whitespace
    collapse to underscores. The result is a single basename, not a path.
    """

    if value is None:
        return ""
    name = Path(str(value)).name
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    if not name or name in {".", ".."}:
        return ""
    return name[:max_length]
