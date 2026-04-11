"""Tests for Dongtian memory prompt injection."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from openharness.config.settings import MemorySettings, Settings
from openharness.prompts import build_runtime_system_prompt


def _fts5_available() -> bool:
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(content)")
        conn.close()
        return True
    except sqlite3.OperationalError:
        return False


def _create_dongtian_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE wings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wing_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(wing_id, name)
        );

        CREATE TABLE drawers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            source TEXT,
            source_ts TEXT
        );

        CREATE VIRTUAL TABLE drawers_fts USING fts5(
            content, source, content=drawers, content_rowid=id
        );
        """
    )
    wing_id = conn.execute("INSERT INTO wings (name) VALUES (?)", ("codex-project",)).lastrowid
    room_id = conn.execute(
        "INSERT INTO rooms (wing_id, name) VALUES (?, ?)",
        (wing_id, "2026-04-01"),
    ).lastrowid
    drawer_content = "User: Please explain the factor pipeline architecture.\n\nAssistant: Sure..."
    drawer_id = conn.execute(
        "INSERT INTO drawers (room_id, content, source, source_ts) VALUES (?, ?, ?, ?)",
        (room_id, drawer_content, "codex:deadbeef", "2026-04-01T00:00:00Z"),
    ).lastrowid
    conn.execute(
        "INSERT INTO drawers_fts(rowid, content, source) VALUES (?, ?, ?)",
        (drawer_id, drawer_content, "codex:deadbeef"),
    )
    conn.commit()
    conn.close()


@pytest.mark.skipif(not _fts5_available(), reason="SQLite FTS5 not available")
def test_build_runtime_system_prompt_injects_dongtian_snippets(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    repo = tmp_path / "repo"
    repo.mkdir()

    db_path = tmp_path / "palace.db"
    _create_dongtian_db(db_path)

    settings = Settings(
        memory=MemorySettings(
            enabled=True,
            dongtian_enabled=True,
            dongtian_db_path=str(db_path),
            dongtian_limit=3,
            dongtian_max_chars=2000,
        )
    )

    prompt = build_runtime_system_prompt(settings, cwd=repo, latest_user_prompt="factor pipeline")

    assert "Relevant Dongtian Memories" in prompt
    assert "factor pipeline architecture" in prompt
    assert "codex-project" in prompt
    assert "2026-04-01" in prompt


def test_build_runtime_system_prompt_does_not_inject_dongtian_by_default(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    repo = tmp_path / "repo"
    repo.mkdir()

    prompt = build_runtime_system_prompt(Settings(), cwd=repo, latest_user_prompt="factor pipeline")

    assert "Relevant Dongtian Memories" not in prompt

