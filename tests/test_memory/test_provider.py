"""Tests for the memory provider protocol and registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.memory import (
    LocalMarkdownProvider,
    MemoryResult,
    get_memory_provider,
    known_memory_providers,
    register_memory_provider,
)
from openharness.memory.providers.base import clear_memory_providers


@pytest.fixture
def isolated_registry():
    """Give each test a fresh registry with just the built-in 'local' provider."""
    clear_memory_providers()
    register_memory_provider("local", LocalMarkdownProvider)
    yield
    clear_memory_providers()
    register_memory_provider("local", LocalMarkdownProvider)


# --- MemoryResult -----------------------------------------------------------


def test_memory_result_defaults_are_sensible():
    result = MemoryResult(id="x.md", title="x", content="body")
    assert result.description == ""
    assert result.score is None
    assert result.source == ""
    assert result.metadata == {}


def test_memory_result_is_hashable_via_frozen_dataclass():
    # Frozen dataclasses let callers use MemoryResult in dedupe sets when
    # the metadata dict is empty (i.e. for the common case).
    a = MemoryResult(id="a.md", title="a", content="hello")
    b = MemoryResult(id="a.md", title="a", content="hello")
    assert a == b


# --- Registry ---------------------------------------------------------------


def test_local_provider_registered_by_default():
    # No fixture: just importing openharness.memory should register 'local'.
    assert "local" in known_memory_providers()


def test_register_and_get_provider(isolated_registry):
    class FakeProvider:
        name = "fake"

        def __init__(self, greeting: str = "hi"):
            self.greeting = greeting

        def search(self, query, *, cwd, limit=5):
            return [MemoryResult(id="f", title=self.greeting, content=query)]

        def close(self):
            return None

    register_memory_provider("fake", FakeProvider)

    provider = get_memory_provider("fake")
    results = provider.search("query", cwd="/tmp")
    assert results[0].content == "query"
    assert results[0].title == "hi"


def test_get_provider_forwards_settings_kwargs(isolated_registry):
    class ConfigurableProvider:
        name = "configurable"

        def __init__(self, *, url: str, timeout: float = 1.0):
            self.url = url
            self.timeout = timeout

        def search(self, query, *, cwd, limit=5):
            return []

        def close(self):
            return None

    register_memory_provider("configurable", ConfigurableProvider)

    class _Settings:
        class _Mem:
            providers = {"configurable": {"url": "https://mem", "timeout": 5.0}}

        memory = _Mem()

    provider = get_memory_provider("configurable", settings=_Settings())
    assert isinstance(provider, ConfigurableProvider)
    assert provider.url == "https://mem"
    assert provider.timeout == 5.0


def test_get_provider_unknown_backend_lists_known(isolated_registry):
    with pytest.raises(ValueError) as exc:
        get_memory_provider("does-not-exist")
    # The error must be actionable — it should list what *is* available so
    # users can fix settings.json without reading the source.
    assert "does-not-exist" in str(exc.value)
    assert "local" in str(exc.value)


def test_register_rejects_empty_name(isolated_registry):
    with pytest.raises(ValueError):
        register_memory_provider("", LocalMarkdownProvider)


def test_register_rejects_duplicate(isolated_registry):
    with pytest.raises(ValueError):
        register_memory_provider("local", LocalMarkdownProvider)


# --- LocalMarkdownProvider --------------------------------------------------


def _write_memory(project_dir: Path, filename: str, body: str) -> Path:
    from openharness.memory.paths import get_project_memory_dir

    memory_dir = get_project_memory_dir(project_dir)
    path = memory_dir / filename
    path.write_text(body, encoding="utf-8")
    return path


def test_local_provider_populates_content_and_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()
    _write_memory(
        project,
        "auth_rewrite.md",
        "---\nname: auth-rewrite\ndescription: Auth middleware rewrite\ntype: project\n---\n"
        "Session token storage rework.\n",
    )

    provider = LocalMarkdownProvider()
    results = provider.search("auth middleware", cwd=project)

    assert results
    top = results[0]
    assert top.content.startswith("---")
    assert "Session token storage rework" in top.content
    assert top.source == "local"
    assert top.metadata["memory_type"] == "project"
    assert top.metadata["path"].endswith("auth_rewrite.md")


def test_local_provider_matches_find_relevant_memories_ordering(tmp_path, monkeypatch):
    """The provider layer must not change the default search ranking."""
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()
    _write_memory(
        project,
        "cache_layer.md",
        "---\nname: cache-layer\ndescription: Redis caching strategy\n---\nNotes.\n",
    )
    _write_memory(
        project,
        "infra_notes.md",
        "---\nname: infra-notes\ndescription: Infrastructure overview\n---\n"
        "We use redis for sessions.\n",
    )

    from openharness.memory import find_relevant_memories

    legacy = find_relevant_memories("redis caching", project)
    provider_results = LocalMarkdownProvider().search("redis caching", cwd=project)

    assert [r.metadata["path"] for r in provider_results] == [str(h.path) for h in legacy]


def test_local_provider_respects_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()
    for i in range(5):
        _write_memory(
            project,
            f"note_{i}.md",
            f"---\nname: note-{i}\ndescription: pytest fixtures {i}\n---\nBody.\n",
        )

    results = LocalMarkdownProvider().search("pytest fixtures", cwd=project, limit=2)
    assert len(results) == 2


def test_local_provider_close_is_noop():
    # close() on a stateless provider must be safe to call repeatedly.
    provider = LocalMarkdownProvider()
    provider.close()
    provider.close()


# --- Integration with build_runtime_system_prompt ---------------------------


def test_build_runtime_prompt_uses_provider_for_memory_section(tmp_path, monkeypatch):
    """End-to-end: the provider path produces the same 'Relevant Memories'
    section the pre-provider code produced.
    """
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()
    _write_memory(
        project,
        "kubectl_tips.md",
        "---\nname: kubectl-tips\ndescription: kubectl rollout patterns\n---\n"
        "Use rollout status.\n",
    )

    from openharness.config.settings import Settings
    from openharness.prompts.context import build_runtime_system_prompt

    settings = Settings()
    prompt = build_runtime_system_prompt(
        settings,
        cwd=project,
        latest_user_prompt="kubectl rollout help",
    )

    assert "# Relevant Memories" in prompt
    assert "kubectl_tips.md" in prompt
    assert "Use rollout status" in prompt


def test_build_runtime_prompt_falls_back_on_unknown_backend(tmp_path, monkeypatch, caplog):
    """A misconfigured backend must not fail prompt assembly — it logs and
    omits the Relevant Memories section.
    """
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()
    _write_memory(
        project,
        "note.md",
        "---\nname: note\ndescription: something\n---\nbody\n",
    )

    from openharness.config.settings import Settings
    from openharness.prompts.context import build_runtime_system_prompt

    settings = Settings()
    settings.memory.backend = "not-registered"

    with caplog.at_level("WARNING"):
        prompt = build_runtime_system_prompt(
            settings,
            cwd=project,
            latest_user_prompt="something",
        )

    assert "# Relevant Memories" not in prompt
    assert any("not-registered" in record.message for record in caplog.records)


def test_build_runtime_prompt_falls_back_when_provider_raises(
    tmp_path, monkeypatch, caplog, isolated_registry
):
    """Provider exceptions during search must not crash prompt assembly."""
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()

    class BrokenProvider:
        name = "broken"

        def search(self, query, *, cwd, limit=5):
            raise RuntimeError("boom")

        def close(self):
            return None

    register_memory_provider("broken", BrokenProvider)

    from openharness.config.settings import Settings
    from openharness.prompts.context import build_runtime_system_prompt

    settings = Settings()
    settings.memory.backend = "broken"

    with caplog.at_level("WARNING"):
        prompt = build_runtime_system_prompt(
            settings,
            cwd=project,
            latest_user_prompt="anything",
        )

    assert "# Relevant Memories" not in prompt
    assert any("broken" in record.message and "boom" in record.message for record in caplog.records)
