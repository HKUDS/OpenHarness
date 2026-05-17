"""Tests for memory helpers."""

from __future__ import annotations

from pathlib import Path

from openharness.memory import (
    add_memory_entry,
    find_relevant_memories,
    get_memory_entrypoint,
    get_project_memory_dir,
    load_memory_prompt,
    migrate_memory,
    remove_memory_entry,
)
from openharness.memory.scan import _parse_memory_file, scan_memory_files
from openharness.memory.usage import find_stale_memory_candidates, load_usage_index, mark_memory_used


def test_memory_paths_are_stable(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    memory_dir = get_project_memory_dir(project_dir)
    entrypoint = get_memory_entrypoint(project_dir)

    assert memory_dir.exists()
    assert entrypoint.parent == memory_dir


def test_load_memory_prompt_includes_entrypoint(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    entrypoint = get_memory_entrypoint(project_dir)
    entrypoint.write_text("# Index\n- [Testing](testing.md)\n", encoding="utf-8")

    prompt = load_memory_prompt(project_dir)

    assert prompt is not None
    assert "Persistent memory directory" in prompt
    assert "Testing" in prompt


def test_find_relevant_memories(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    memory_dir = get_project_memory_dir(project_dir)
    (memory_dir / "pytest_tips.md").write_text("Pytest markers and fixtures\n", encoding="utf-8")
    (memory_dir / "docker_notes.md").write_text("Docker compose caveats\n", encoding="utf-8")

    matches = find_relevant_memories("fix pytest fixtures", project_dir)

    assert matches
    assert matches[0].path.name == "pytest_tips.md"


def test_add_memory_entry_writes_schema_and_dedupes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    first = add_memory_entry(project_dir, "Pytest Tips", "Use fixtures for setup.")
    second = add_memory_entry(project_dir, "Pytest Tips Copy", "Use fixtures for setup.")

    assert second == first
    headers = scan_memory_files(project_dir)
    assert len(headers) == 1
    assert headers[0].id.startswith("mem-")
    assert headers[0].schema_version == 1
    assert headers[0].source == "manual"
    assert headers[0].importance == 1
    assert headers[0].signature


def test_remove_memory_entry_soft_deletes_and_hides_entry(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    path = add_memory_entry(project_dir, "Remove Me", "temporary note")

    assert remove_memory_entry(project_dir, "remove_me") is True
    assert path.exists()
    assert scan_memory_files(project_dir) == []
    headers = scan_memory_files(project_dir, include_disabled=True)
    assert len(headers) == 1
    assert headers[0].disabled is True


def test_migrate_memory_backfills_schema(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    memory_dir = get_project_memory_dir(project_dir)
    legacy = memory_dir / "legacy.md"
    legacy.write_text("Legacy deployment note.\n", encoding="utf-8")

    dry_run = migrate_memory(project_dir, apply=False)

    assert dry_run.dry_run is True
    assert dry_run.changed == 1
    assert "schema_version" not in legacy.read_text(encoding="utf-8")

    applied = migrate_memory(project_dir, apply=True)

    assert applied.dry_run is False
    assert applied.changed == 1
    assert applied.backup_dir
    migrated = legacy.read_text(encoding="utf-8")
    assert "schema_version: 1" in migrated
    assert "source: \"migration\"" in migrated
    assert "Legacy deployment note." in migrated

    rerun = migrate_memory(project_dir, apply=False)
    assert rerun.changed == 0


def test_usage_index_marks_recalled_memories_and_stale_candidates(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    memory_dir = get_project_memory_dir(project_dir)
    (memory_dir / "old.md").write_text(
        "---\n"
        "schema_version: 1\n"
        "id: \"mem-old\"\n"
        "name: \"old\"\n"
        "description: \"old note\"\n"
        "type: \"project\"\n"
        "category: \"knowledge\"\n"
        "importance: 1\n"
        "source: \"test\"\n"
        "signature: \"sig-old\"\n"
        "created_at: \"2020-01-01T00:00:00Z\"\n"
        "updated_at: \"2020-01-01T00:00:00Z\"\n"
        "ttl_days: null\n"
        "disabled: false\n"
        "supersedes: []\n"
        "---\n\n"
        "Old content.\n",
        encoding="utf-8",
    )
    header = scan_memory_files(project_dir)[0]

    assert [item.id for item in find_stale_memory_candidates(project_dir)] == ["mem-old"]

    mark_memory_used(project_dir, [header])
    index = load_usage_index(project_dir)

    assert index["memories"]["mem-old"]["use_count"] == 1
    assert find_stale_memory_candidates(project_dir) == []


# --- Frontmatter parsing tests ---


def test_parse_frontmatter_extracts_fields(tmp_path: Path):
    path = tmp_path / "project_auth.md"
    path.write_text(
        "---\n"
        "name: auth-rewrite\n"
        "description: Auth middleware driven by compliance\n"
        "type: project\n"
        "---\n"
        "\n"
        "Session token storage rework for legal team.\n",
        encoding="utf-8",
    )

    header = _parse_memory_file(path, path.read_text(encoding="utf-8"))

    assert header.title == "auth-rewrite"
    assert header.description == "Auth middleware driven by compliance"
    assert header.memory_type == "project"
    assert "Session token storage" in header.body_preview


def test_parse_frontmatter_falls_back_without_frontmatter(tmp_path: Path):
    path = tmp_path / "quick_note.md"
    path.write_text("Redis cache invalidation strategy\n\nDetails here.\n", encoding="utf-8")

    header = _parse_memory_file(path, path.read_text(encoding="utf-8"))

    assert header.title == "quick_note"
    assert header.description == "Redis cache invalidation strategy"
    assert header.memory_type == ""
    # Description line must not be duplicated into body_preview.
    assert header.body_preview == "Details here."


def test_parse_malformed_frontmatter_does_not_return_delimiter(tmp_path: Path):
    """Unclosed frontmatter must not leak '---' into description."""
    path = tmp_path / "broken.md"
    path.write_text("---\nname: oops\nActual content here.\n", encoding="utf-8")

    header = _parse_memory_file(path, path.read_text(encoding="utf-8"))

    # The key invariant: description is never the raw delimiter.
    assert header.description != "---"
    assert header.description  # non-empty


def test_parse_frontmatter_skips_headings_for_description(tmp_path: Path):
    path = tmp_path / "notes.md"
    path.write_text("# My Heading\n\nActual description here.\n", encoding="utf-8")

    header = _parse_memory_file(path, path.read_text(encoding="utf-8"))

    assert header.description == "Actual description here."


def test_parse_frontmatter_handles_quoted_values(tmp_path: Path):
    path = tmp_path / "quoted.md"
    path.write_text(
        '---\nname: "my-project"\ndescription: \'A quoted desc\'\ntype: feedback\n---\nBody.\n',
        encoding="utf-8",
    )

    header = _parse_memory_file(path, path.read_text(encoding="utf-8"))

    assert header.title == "my-project"
    assert header.description == "A quoted desc"
    assert header.memory_type == "feedback"


def test_scan_memory_files_with_frontmatter(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    memory_dir = get_project_memory_dir(project_dir)
    (memory_dir / "topic.md").write_text(
        "---\nname: my-topic\ndescription: Important topic\ntype: reference\n---\nContent.\n",
        encoding="utf-8",
    )

    headers = scan_memory_files(project_dir)

    assert len(headers) == 1
    assert headers[0].title == "my-topic"
    assert headers[0].description == "Important topic"
    assert headers[0].memory_type == "reference"


# --- Search relevance tests ---


def test_search_prefers_metadata_over_body(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    memory_dir = get_project_memory_dir(project_dir)

    # File A: "redis" appears in frontmatter description
    (memory_dir / "a_redis.md").write_text(
        "---\nname: cache-layer\ndescription: Redis caching strategy\n---\nGeneral notes.\n",
        encoding="utf-8",
    )
    # File B: "redis" appears only in body
    (memory_dir / "b_infra.md").write_text(
        "---\nname: infra-notes\ndescription: Infrastructure overview\n---\nWe use redis for sessions.\n",
        encoding="utf-8",
    )

    matches = find_relevant_memories("redis caching", project_dir)

    assert len(matches) == 2
    assert matches[0].title == "cache-layer"


def test_search_finds_body_content(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    memory_dir = get_project_memory_dir(project_dir)
    (memory_dir / "deploy.md").write_text(
        "---\nname: deploy\ndescription: Deployment notes\n---\nKubernetes rollout strategy details.\n",
        encoding="utf-8",
    )

    matches = find_relevant_memories("kubernetes rollout", project_dir)

    assert matches
    assert matches[0].title == "deploy"


def test_search_handles_cjk_queries(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    memory_dir = get_project_memory_dir(project_dir)
    (memory_dir / "chinese_note.md").write_text(
        "---\nname: meeting\ndescription: 项目会议纪要\n---\n讨论了部署计划。\n",
        encoding="utf-8",
    )

    matches = find_relevant_memories("会议", project_dir)

    assert matches
    assert matches[0].title == "meeting"
