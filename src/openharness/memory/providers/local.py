"""Default memory provider backed by project-local markdown files."""

from __future__ import annotations

from pathlib import Path

from openharness.memory.providers.base import MemoryResult
from openharness.memory.search import find_relevant_memories


class LocalMarkdownProvider:
    """Wrap :func:`openharness.memory.search.find_relevant_memories`.

    The prompt injection produced by this provider is byte-for-byte identical
    to the pre-provider path — the existing integration test in
    ``tests/test_memory/test_memdir.py`` already pins the underlying search
    behavior. Swapping it out with a remote provider is therefore a
    zero-risk change for existing users who keep ``memory.backend = "local"``.
    """

    name = "local"

    def search(
        self,
        query: str,
        *,
        cwd: str | Path,
        limit: int = 5,
    ) -> list[MemoryResult]:
        headers = find_relevant_memories(query, cwd, max_results=limit)
        results: list[MemoryResult] = []
        for header in headers:
            try:
                content = header.path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                # Skip unreadable files; scan.py already filtered most of
                # these, but a race with deletion is still possible.
                continue
            results.append(
                MemoryResult(
                    id=header.path.name,
                    title=header.path.name,
                    content=content,
                    description=header.description,
                    source=self.name,
                    metadata={
                        "memory_type": header.memory_type,
                        "path": str(header.path),
                    },
                )
            )
        return results

    def close(self) -> None:
        return None
