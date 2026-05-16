"""Tests for memory helpers."""

from __future__ import annotations

from pathlib import Path

from openharness.config.paths import use_memory_store_dir
from openharness.memory import (
    add_memory_entry,
    find_relevant_memories,
    get_memory_entrypoint,
    get_project_memory_entries_dir,
    get_project_memory_dir,
    list_memory_files,
    load_memory_prompt,
    upsert_memory_entry,
)
from openharness.memory.paths import get_memory_metadata_index
from openharness.memory.scan import _parse_memory_file, scan_memory_files


def test_memory_paths_are_stable(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    memory_dir = get_project_memory_dir(project_dir)
    entries_dir = get_project_memory_entries_dir(project_dir)
    entrypoint = get_memory_entrypoint(project_dir)

    assert memory_dir.exists()
    assert entries_dir.parent == memory_dir
    assert entrypoint.parent == memory_dir


def test_memory_paths_can_be_redirected_into_ohmo_workspace(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    workspace_memory = tmp_path / ".ohmo-home" / "memory"

    with use_memory_store_dir(workspace_memory, shared_root=True):
        memory_dir = get_project_memory_dir(project_dir)
        entries_dir = get_project_memory_entries_dir(project_dir)

    assert memory_dir == workspace_memory
    assert entries_dir.parent == memory_dir


def test_memory_paths_migrate_legacy_project_dir_into_redirected_root(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    legacy_dir = get_project_memory_dir(project_dir)
    legacy_entry = legacy_dir / "MEMORY.md"
    legacy_child = legacy_dir / "legacy.md"
    legacy_child.write_text("Use ssh legacy@example.com for the older environment.\n", encoding="utf-8")
    legacy_entry.write_text("# Memory Index\n- [Legacy](legacy.md)\n", encoding="utf-8")

    workspace_memory = tmp_path / ".ohmo-home" / "memory"
    with use_memory_store_dir(workspace_memory, shared_root=True):
        memory_dir = get_project_memory_dir(project_dir)
        entrypoint = get_memory_entrypoint(project_dir)
        files = list_memory_files(project_dir)

    assert memory_dir == workspace_memory
    assert files and files[0].parent == workspace_memory / "entries"
    entrypoint_text = entrypoint.read_text(encoding="utf-8")
    assert "Legacy" in entrypoint_text
    assert "entries/legacy" in entrypoint_text
    assert not legacy_dir.exists()


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
    assert "Child memory entries directory" in prompt
    assert "Treat MEMORY.md as the default index" in prompt
    assert "read that child file on demand" in prompt


def test_find_relevant_memories(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    upsert_memory_entry(
        project_dir,
        key="project:pytest_tips",
        title="Pytest Tips",
        description="Testing tips",
        memory_type="project",
        content="Pytest markers and fixtures\nUse fixture scopes carefully.",
    )
    upsert_memory_entry(
        project_dir,
        key="project:docker_notes",
        title="Docker Notes",
        description="Container notes",
        memory_type="project",
        content="Docker compose caveats\nWatch bind mounts on Linux.",
    )

    matches = find_relevant_memories("fix pytest fixtures", project_dir)

    assert matches
    assert matches[0].path.name == "project_pytest_tips.md"


# --- Frontmatter parsing tests ---


def test_parse_frontmatter_extracts_fields(tmp_path: Path):
    path = tmp_path / "project_auth.md"
    path.write_text(
        "---\n"
        "key: project:auth\n"
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
    assert header.memory_key == "project:auth"
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
    upsert_memory_entry(
        project_dir,
        key="reference:topic",
        title="my-topic",
        description="Important topic",
        memory_type="reference",
        content="Content.",
    )

    headers = scan_memory_files(project_dir)

    assert len(headers) == 1
    assert headers[0].title == "my-topic"
    assert headers[0].description == "Important topic"
    assert headers[0].memory_type == "reference"


def test_upsert_memory_entry_merges_semantic_duplicates(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    memory_dir = get_project_memory_dir(project_dir)
    entrypoint = get_memory_entrypoint(project_dir)

    first = memory_dir / "memory.md"
    first.write_text(
        "---\n"
        "key: guardrail:migration_and_release_protection\n"
        "name: 保护迁移文件和发布配置\n"
        "description: 迁移文件和发布配置受保护，不能删除或擅自更改。\n"
        "type: guardrail\n"
        "---\n"
        "本仓库的迁移文件和发布配置是受保护的，不得删除、移动或未经明确确认进行更改。\n",
        encoding="utf-8",
    )
    second = memory_dir / "memory_guardrail_no_delete_.md"
    second.write_text(
        "---\n"
        "key: guardrail:no_delete_migration_release_config\n"
        "name: 保护迁移文件和发布配置\n"
        "description: 迁移文件和发布配置未经确认不可删除。\n"
        "type: guardrail\n"
        "---\n"
        "仓库中的迁移文件和发布配置未经明确确认，不得删除。\n",
        encoding="utf-8",
    )
    entrypoint.write_text(
        "# Memory Index\n"
        "- [保护迁移文件和发布配置](memory.md)\n"
        "- [保护迁移文件和发布配置](memory_guardrail_no_delete_.md)\n",
        encoding="utf-8",
    )

    path, status = upsert_memory_entry(
        project_dir,
        key="guardrail:migration_and_release_protection",
        title="保护迁移文件和发布配置",
        description="迁移文件和发布配置未经确认不可删除。",
        memory_type="guardrail",
        content="仓库中的迁移文件和发布配置未经明确确认，不得删除、移动或改动。",
    )

    assert status == "updated"
    assert path.exists()
    files = list_memory_files(project_dir)
    assert len(files) == 1
    assert files[0] == path
    assert "不得删除、移动或改动" in path.read_text(encoding="utf-8")
    index_text = entrypoint.read_text(encoding="utf-8")
    assert index_text.count("[保护迁移文件和发布配置]") == 1


def test_upsert_memory_entry_uses_english_key_slug_for_filename(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    entrypoint = get_memory_entrypoint(project_dir)

    path, status = upsert_memory_entry(
        project_dir,
        key="preference:reply_language_should_be_chinese_by_default_even_when_key_is_long",
        title="默认回复语言为中文",
        description="默认使用中文回复。",
        memory_type="preference",
        content="默认回复语言为中文，除非用户明确要求其他语言。",
    )

    assert status == "created"
    assert path.parent == get_project_memory_entries_dir(project_dir)
    assert path.name.startswith("preference_reply_language_should_be_chinese_by_default")
    assert path.name.endswith(".md")
    assert entrypoint.read_text(encoding="utf-8").strip().endswith(f"[默认回复语言为中文](entries/{path.name})")


def test_scan_memory_files_uses_metadata_index_without_reopening_entries(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    path, _ = upsert_memory_entry(
        project_dir,
        key="guardrail:never_delete_migrations",
        title="保护迁移文件",
        description="迁移文件不能删除。",
        memory_type="guardrail",
        content="Guardrail: never delete migrations/",
    )

    metadata_index = get_memory_metadata_index(project_dir)
    assert metadata_index.exists()

    original_read_text = Path.read_text

    def _guarded_read_text(self: Path, *args, **kwargs):
        if self == path:
            raise AssertionError("scan_memory_files should use the metadata index for current entries")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _guarded_read_text)

    headers = scan_memory_files(project_dir, max_files=None)

    assert len(headers) == 1
    assert headers[0].memory_key == "guardrail:never_delete_migrations"


def test_scan_memory_files_rebuilds_from_memory_md_without_opening_entries(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    path, _ = upsert_memory_entry(
        project_dir,
        key="guardrail:never_delete_migrations",
        title="保护迁移文件",
        description="旧描述",
        memory_type="guardrail",
        content="Guardrail: never delete migrations/",
    )

    metadata_index = get_memory_metadata_index(project_dir)
    metadata_index.unlink()

    original_read_text = Path.read_text

    def _guarded_read_text(self: Path, *args, **kwargs):
        if self == path:
            raise AssertionError("scan_memory_files should rebuild from MEMORY.md without reopening child entries")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _guarded_read_text)

    headers = scan_memory_files(project_dir, max_files=None)

    assert len(headers) == 1
    assert headers[0].title == "保护迁移文件"
    assert headers[0].path == path
    assert headers[0].description == ""
    assert headers[0].body_preview == ""


def test_add_memory_entry_uses_entries_dir_and_english_collision_suffix(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    first = add_memory_entry(project_dir, "Pytest Tips", "use fixtures")
    second = add_memory_entry(project_dir, "Pytest Tips", "still use fixtures, but for another note")

    assert first.parent == get_project_memory_entries_dir(project_dir)
    assert first.name == "pytest_tips.md"
    assert second.parent == get_project_memory_entries_dir(project_dir)
    assert second.name.startswith("pytest_tips_")
    assert second.name.endswith(".md")
    suffix = second.stem.removeprefix("pytest_tips_")
    assert len(suffix) == 8
    assert all(char in "0123456789abcdef" for char in suffix)


# --- Search relevance tests ---


def test_search_prefers_metadata_over_body(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    # File A: "redis" appears in frontmatter description
    upsert_memory_entry(
        project_dir,
        key="project:cache_layer",
        title="cache-layer",
        description="Redis caching strategy",
        memory_type="project",
        content="General notes.",
    )
    # File B: "redis" appears only in body
    upsert_memory_entry(
        project_dir,
        key="project:infra_notes",
        title="infra-notes",
        description="Infrastructure overview",
        memory_type="project",
        content="General notes.\nWe use redis for sessions.",
    )

    matches = find_relevant_memories("redis caching", project_dir)

    assert len(matches) == 2
    assert matches[0].title == "cache-layer"


def test_search_finds_body_content(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    upsert_memory_entry(
        project_dir,
        key="project:deploy",
        title="deploy",
        description="Deployment notes",
        memory_type="project",
        content="General deployment context.\nKubernetes rollout strategy details.",
    )

    matches = find_relevant_memories("kubernetes rollout", project_dir)

    assert matches
    assert matches[0].title == "deploy"


def test_search_handles_cjk_queries(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    upsert_memory_entry(
        project_dir,
        key="project:meeting",
        title="meeting",
        description="项目会议纪要",
        memory_type="project",
        content="讨论了部署计划。",
    )

    matches = find_relevant_memories("会议", project_dir)

    assert matches
    assert matches[0].title == "meeting"
