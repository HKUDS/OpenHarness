"""Tests for memory provider delegation."""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.memory import register_memory_provider, reset_memory_provider_registry, unregister_memory_provider
from openharness.memory.manager import add_memory_entry, list_memory_files, remove_memory_entry, upsert_memory_entry
from openharness.memory.scan import scan_memory_files
from openharness.memory.types import MemoryHeader
from openharness.tools.base import ToolExecutionContext
from openharness.tools.memory_write_tool import MemoryWriteTool, MemoryWriteToolInput


class RecordingMemoryProvider:
    def __init__(self, repo: Path) -> None:
        self.repo = repo.resolve()
        self.calls: list[tuple] = []
        self.memory_path = self.repo / "provider-memory.md"
        self.headers = [
            MemoryHeader(
                path=self.memory_path,
                title="Provider note",
                description="Recorded by provider",
                modified_at=123.0,
                memory_type="project",
                memory_key="project:provider",
                body_preview="Provider preview",
            )
        ]

    def scan_memory_files(self, cwd: str | Path, *, max_files: int | None = 50) -> list[MemoryHeader]:
        self.calls.append(("scan", Path(cwd).resolve(), max_files))
        if max_files is None:
            return list(self.headers)
        return list(self.headers[:max_files])

    def list_memory_files(self, cwd: str | Path) -> list[Path]:
        self.calls.append(("list", Path(cwd).resolve()))
        return [self.memory_path]

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
        self.calls.append(
            ("upsert", Path(cwd).resolve(), key, title, content, description, memory_type)
        )
        return self.memory_path, "updated"

    def add_memory_entry(self, cwd: str | Path, title: str, content: str) -> Path:
        self.calls.append(("add", Path(cwd).resolve(), title, content))
        return self.repo / "manual-provider-memory.md"

    def remove_memory_entry(self, cwd: str | Path, name: str) -> bool:
        self.calls.append(("remove", Path(cwd).resolve(), name))
        return True


def test_memory_provider_registry_delegates_manager_and_scan_calls(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    provider = RecordingMemoryProvider(repo)
    register_memory_provider(repo, provider)

    try:
        headers = scan_memory_files(repo, max_files=1)
        listed = list_memory_files(repo)
        path, status = upsert_memory_entry(
            repo,
            key="project:provider",
            title="Provider note",
            content="Provider-backed content.",
            description="Recorded by provider",
            memory_type="project",
        )
        added = add_memory_entry(repo, "Manual note", "Manual content")
        removed = remove_memory_entry(repo, "project:provider")
    finally:
        unregister_memory_provider(repo)
        reset_memory_provider_registry()

    assert [header.title for header in headers] == ["Provider note"]
    assert listed == [repo / "provider-memory.md"]
    assert path == repo / "provider-memory.md"
    assert status == "updated"
    assert added == repo / "manual-provider-memory.md"
    assert removed is True
    assert provider.calls == [
        ("scan", repo.resolve(), 1),
        ("list", repo.resolve()),
        (
            "upsert",
            repo.resolve(),
            "project:provider",
            "Provider note",
            "Provider-backed content.",
            "Recorded by provider",
            "project",
        ),
        ("add", repo.resolve(), "Manual note", "Manual content"),
        ("remove", repo.resolve(), "project:provider"),
    ]


@pytest.mark.asyncio
async def test_memory_write_tool_uses_registered_memory_provider(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    provider = RecordingMemoryProvider(repo)
    register_memory_provider(repo, provider)

    try:
        result = await MemoryWriteTool().execute(
            MemoryWriteToolInput(
                key="project:provider",
                title="Provider note",
                description="Recorded by provider",
                memory_type="project",
                content="Provider-backed content.",
            ),
            ToolExecutionContext(cwd=repo),
        )
    finally:
        unregister_memory_provider(repo)
        reset_memory_provider_registry()

    assert result.is_error is False
    assert result.output == "Updated durable memory provider-memory.md"
    assert provider.calls == [
        (
            "upsert",
            repo.resolve(),
            "project:provider",
            "Provider note",
            "Provider-backed content.",
            "Recorded by provider",
            "project",
        )
    ]