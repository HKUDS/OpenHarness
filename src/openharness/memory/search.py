"""Simple heuristic memory search."""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

from openharness.memory.scan import scan_memory_files
from openharness.memory.schema import parse_datetime, utc_now
from openharness.memory.types import MemoryHeader
from openharness.memory.usage import get_memory_usage


def find_relevant_memories(
    query: str,
    cwd: str | Path,
    *,
    max_results: int = 5,
) -> list[MemoryHeader]:
    """Return the memory files whose metadata and content overlap the query.

    Scoring weights frontmatter fields higher than body content so that
    well-annotated memories surface first.
    """
    tokens = _tokenize(query)
    if not tokens:
        return []

    scored: list[tuple[float, MemoryHeader]] = []
    for header in scan_memory_files(cwd, max_files=100):
        meta = f"{header.title} {header.description}".lower()
        body = header.body_preview.lower()

        # Metadata matches are weighted 2x; body matches 1x.
        meta_hits = sum(1 for t in tokens if t in meta)
        body_hits = sum(1 for t in tokens if t in body)
        usage = get_memory_usage(cwd, header.id, memory_dir=header.path.parent)
        score = (
            meta_hits * 2.0
            + body_hits
            + header.importance * 0.4
            + min(int(usage["use_count"]), 5) * 0.1
            + _recency_boost(header)
        )
        if meta_hits or body_hits:
            scored.append((score, header))

    scored.sort(key=lambda item: (-item[0], -item[1].modified_at))
    return [header for _, header in scored[:max_results]]


def _tokenize(text: str) -> set[str]:
    """Extract search tokens from *text*, handling ASCII and Han ideographs."""
    # ASCII word tokens (3+ chars)
    ascii_tokens = {t for t in re.findall(r"[A-Za-z0-9_]+", text.lower()) if len(t) >= 3}
    # Han ideographs (each character carries independent meaning)
    han_chars = set(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))
    return ascii_tokens | han_chars


def _recency_boost(header: MemoryHeader) -> float:
    timestamp = parse_datetime(header.updated_at) or parse_datetime(header.created_at)
    if timestamp is None:
        return 0.0
    age = utc_now() - timestamp
    if age <= timedelta(days=14):
        return 0.3
    if age <= timedelta(days=30):
        return 0.1
    return 0.0
